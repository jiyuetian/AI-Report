"""
/brain/run SSE - M2-08 (R1返工: 接入真实大脑)
五阶段进度流式回传（对应Loading页五阶段）
"""
import asyncio
import json
import os
import traceback
import uuid
import re
from typing import AsyncGenerator, Dict, Any, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from app.core.database import async_session_factory
from app.core.security import get_current_user
from app.core.brain_config_manager import BrainTraceManager
from app.core.duckdb_manager import get_duckdb
from app.core.config import settings
from app.core.brain_modules import (
    detect_theme, generate_analysis_goals, generate_charts_with_llm,
    orchestrate_and_score
)
from app.core.token_manager import TokenManager
from app.core.version_manager import VersionManager
from app.models.dataset import Dataset
from app.models.dashboard import Dashboard
from app.models.quality import QualityIssue
from app.models.brain import BrainTrace, BrainTraceSummary
from app.api.health import _check_llm_reachable
# Phase 4：Skill 框架接入（planner 驱动能力剪枝 + S1/S2 经 skill 执行，内联兜底）
from app.core.skills.registry import registry
from app.core.skills.planner import SkillPlanner
from app.core.skills.base import SkillContext

router = APIRouter(prefix="/brain", tags=["Brain-Run-SSE"])

# 后台任务注册表：run_id -> asyncio.Task（任务独立于请求生命周期，离开页面不中断）
_RUN_TASKS: Dict[str, asyncio.Task] = {}
# 运行状态快照：run_id -> {status, stage, progress, message, detail}（状态端随时可查）
_RUN_STATUS: Dict[str, Dict[str, Any]] = {}


async def _safe_trace(db, coro, label: str):
    """
    执行一条 BrainTrace 写库操作。
    任何数据库异常（如并发写锁 "database is locked"）都自愈：回滚会话后继续，
    避免一次写失败把整个 Session 置于 pending-rollback，导致后续查询全部报错、
    误报为"理解数据/主题识别失败"。
    """
    try:
        return await coro
    except Exception as e:
        print(f"[Brain] {label} 写库失败(不影响主流程): {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return None


def _short_err(e) -> str:
    """把异常压缩成一行可读原因（去嵌套堆栈，最多160字）"""
    raw = str(e) if e else "未知异常"
    return raw.strip().splitlines()[0][:160] if raw.strip() else "未知异常"


# 数值型 DuckDB 类型关键字（用于判断某列是否可做度量）
_NUMERIC_TYPE_KEYS = (
    "INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL", "BOOL",
)


def _is_numeric_type(col_type: str) -> bool:
    t = str(col_type or "").upper()
    if not t:
        return False
    if "DATE" in t or "TIME" in t or "CHAR" in t or "STRING" in t or "VARCHAR" in t:
        return False
    return any(k in t for k in _NUMERIC_TYPE_KEYS)


def _sanitize_charts(
    charts: list,
    fields: list,
    column_types: dict,
    column_cardinality: Optional[Dict[str, int]] = None,
) -> list:
    """图表消毒层（沿用 InsightDesk 的核心原则：AI 产出不可直信，落库前必须校验）

    规则：
      1. 引用了不存在字段的图表直接丢弃（防止前端取数全空）
      2. 度量列 == 维度列（如 x=婚姻状况 y=婚姻状况）→ 真实意图是「该维度分布计数」
         → 强制 aggregation=count，前端按计数渲染，避免 parseFloat 文本得到 NaN 造成空图
      3. 度量列非数值型且聚合方式为 sum/avg → 同样纠正为 count
      4. 柱状图/饼图缺少维度列 → 丢弃
      5. 柱状图/饼图的维度为单值（唯一值<2）→ 图表无信息量，丢弃（避免空/单条图）
    """
    if not charts:
        return charts
    valid = set(fields or [])
    card = column_cardinality or {}
    out = []
    dropped = 0
    fixed = 0
    for c in charts:
        if not isinstance(c, dict):
            continue
        ctype = str(c.get("chart_type") or "").lower()
        dim = c.get("x_field") or c.get("category_field") or ""
        meas = c.get("y_field") or c.get("value_field") or ""

        # 规则 1：字段存在性
        if dim and valid and dim not in valid:
            dropped += 1
            continue
        if meas and valid and meas not in valid:
            dropped += 1
            continue
        if not dim and not meas:
            dropped += 1
            continue

        # 规则 4：柱状图/饼图必须有维度
        if ctype in ("bar", "pie") and not dim:
            dropped += 1
            continue

        # 规则 5：维度为单值（唯一值<2）→ 无信息量，丢弃
        if ctype in ("bar", "pie") and dim and dim in card and card.get(dim, 99) < 2:
            dropped += 1
            continue

        # 规则 2/3：度量不可用 → 转计数
        need_count = False
        if meas and dim and meas == dim:
            need_count = True
        elif meas and valid and not _is_numeric_type(column_types.get(meas, "")):
            need_count = True
        elif meas and not valid and not _is_numeric_type(column_types.get(meas, "")):
            need_count = True

        if need_count:
            cfg = c.get("config")
            if not isinstance(cfg, dict):
                cfg = {}
                c["config"] = cfg
            if cfg.get("aggregation") != "count":
                cfg["aggregation"] = "count"
                fixed += 1

        out.append(c)

    if dropped or fixed:
        print(f"[Brain] 图表消毒: 保留{len(out)} 丢弃{dropped} 纠正为计数{fixed}")
    return out


def _record_stage_error(run_id: str, stage: str, msg: str) -> None:
    """记录某阶段用户可读的失败消息，供 /status 回传，避免用户只看到笼统报错"""
    _RUN_STATUS.setdefault(run_id, {}).setdefault("stage_errors", {})[stage] = msg


# 用户决策等待表：run_id -> asyncio.Event
# 流水线在 S3 等 AI 失败时会暂停，等待用户经 POST /brain/run/{run_id}/resume 回传选择
_RUN_WAITERS: Dict[str, asyncio.Event] = {}
_RUN_CHOICE: Dict[str, str] = {}


async def _request_user_choice(run_id: str, payload: Dict[str, Any], timeout: Optional[int] = None) -> str:
    """暂停流水线，等待用户通过 /resume 回传选择。

    返回用户选择：'rule_fallback'（规则兜底生成）或 'wait_retry'（等 AI 恢复重试）。
    超时自动兜底为 'rule_fallback'，避免任务永久挂起。
    超时秒数默认 120（生产合理），可用环境变量 BRAIN_AI_CHOICE_TIMEOUT 调整，
    演示现场可设为 30 以缩短等待（如：BRAIN_AI_CHOICE_TIMEOUT=30 启动后端）。
    """
    # M3（拍板2）：默认 120s，可配置；演示时可调短
    if timeout is None:
        _raw = os.getenv("BRAIN_AI_CHOICE_TIMEOUT")
        try:
            timeout = int(_raw) if _raw else 120
        except (TypeError, ValueError):
            timeout = 120
    _RUN_STATUS.setdefault(run_id, {})["ai_awaiting"] = payload
    ev = asyncio.Event()
    _RUN_WAITERS[run_id] = ev
    try:
        await asyncio.wait_for(ev.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        choice = "rule_fallback"
    else:
        choice = _RUN_CHOICE.pop(run_id, "rule_fallback")
    finally:
        _RUN_WAITERS.pop(run_id, None)
        _RUN_STATUS.get(run_id, {}).pop("ai_awaiting", None)
    return choice


def _resume_run_choice(run_id: str, choice: str) -> bool:
    """用户回传选择，唤醒暂停中的流水线。"""
    _RUN_CHOICE[run_id] = choice
    ev = _RUN_WAITERS.get(run_id)
    if ev:
        ev.set()
        return True
    return False


async def _retry_s3_with_ai(run_id, db, theme_tag, fields, goals, grain, reason,
                            max_rounds: int = 3, derived_metrics=None, field_profiles=None):
    """用户选择"等 AI 恢复"后：带退避重试 S3 的 LLM 图表生成。

    某一轮成功（generated_by=='llm'）即返回 (result, ai_failed=False)；
    多轮仍失败则再次把选择权交还用户（可改选规则兜底）。
    返回 (s3_result, ai_failed)。
    """
    from app.core.brain_modules import generate_charts_with_llm
    s3_result = {"charts": [], "generated_by": "rule_engine", "fallback_reason": reason}
    for r in range(max_rounds):
        # 退避：首轮稍短，避免刚限流就猛打；逐轮加长
        await asyncio.sleep(min(8 * (r + 1), 45))
        try:
            res = await generate_charts_with_llm(
                db=db, theme=theme_tag, fields=fields, goals=goals, grain=grain,
                derived_metrics=derived_metrics or {}, field_profiles=field_profiles
            )
        except Exception as e:
            res = {"charts": [], "generated_by": "rule_engine", "fallback_reason": _short_err(e)}
        if res.get("generated_by") == "llm":
            return res, False
        # 仍失败：再问一次用户（可改选规则兜底）
        choice = await _request_user_choice(run_id, {
            "stage": "S3",
            "options": ["rule_fallback", "wait_retry"],
            "reason": res.get("fallback_reason") or "AI 仍未恢复",
            "retry_round": r + 1,
            "message": "AI 仍未恢复（限流或异常）。是否继续等待重试，还是改用规则引擎兜底生成基础看板？"
        })
        if choice == "rule_fallback":
            return res, True
        # 否则继续下一轮重试
    return s3_result, True


async def _run_worker(run_id: str, dataset_id: str, user_id: str) -> None:
    """
    在后台运行 brain 管道并持续刷新状态快照。
    即使前端断开 SSE/离开页面，任务仍在服务端继续，返回后可查询最终结果。
    """
    cache = _RUN_STATUS.setdefault(run_id, {"status": "running", "progress": 0})
    try:
        async for event in brain_run_pipeline(run_id, dataset_id, user_id):
            # 解析管道产出的 SSE 事件字符串，提取状态快照
            data = None
            for line in event.splitlines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:].strip())
                    except Exception:
                        pass
                    break
            if not data:
                continue

            status = "running"
            if data.get("status") == "failed":
                status = "failed"
            elif data.get("stage") == "COMPLETE" and data.get("status") == "completed":
                status = "completed"

            cache.update({
                "status": status,
                "stage": data.get("stage", ""),
                "progress": data.get("progress", cache.get("progress", 0)),
                "message": data.get("message", ""),
                "detail": data.get("detail") or {},
            })

            if status == "failed":
                break
            if status == "completed":
                break
    except asyncio.CancelledError:
        _RUN_STATUS[run_id]["status"] = "cancelled"
        _RUN_STATUS[run_id]["message"] = "任务已被取消"
        raise
    except Exception as e:
        _RUN_STATUS[run_id]["status"] = "failed"
        _RUN_STATUS[run_id]["message"] = f"后台任务异常: {str(e)}"
        _RUN_STATUS[run_id]["detail"] = {"error": str(e)}
        # 2026-09-18 修复：把完整堆栈落到日志，避免「静默卡在 running」无法定位
        print(f"[Brain][WORKER-ERROR] run_id={run_id} dataset_id={dataset_id}\n{traceback.format_exc()}")
    finally:
        _RUN_STATUS[run_id]["finished"] = True
        _RUN_TASKS.pop(run_id, None)


class BrainRunRequest(BaseModel):
    """Brain运行请求"""
    dataset_id: str
    user_id: str = "anonymous"


class StageProgress:
    """阶段进度"""
    def __init__(self, run_id: str, dataset_id: str):
        self.run_id = run_id
        self.dataset_id = dataset_id
        self.current_stage = ""
        self.stage_status = "idle"  # idle/running/completed/failed
        self.progress = 0
        self.message = ""
        self.detail = {}
    
    def to_event(self) -> str:
        """转换为SSE事件格式"""
        data = {
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "stage": self.current_stage,
            "stage_name": self._get_stage_name(self.current_stage),
            "status": self.stage_status,
            "progress": self.progress,
            "message": self.message,
            "detail": self.detail
        }
        return f"event: stage\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    @staticmethod
    def _get_stage_name(stage: str) -> str:
        names = {
            "S1": "主题识别",
            "S2": "目标生成",
            "S3": "图表推荐",
            "S4": "编排优化",
            "S5": "评分验证",
            "COMPLETE": "完成"
        }
        return names.get(stage, stage)


class TokenBudget:
    """单任务 Token 预算（P1-1 取长补短 InsightDesk §3.1）。

    累计一次 /brain/run 生成流水线各阶段的 LLM 消耗（按字符估算），
    达 80% 发一次告警事件，达 100% 置熔断标志——后续 LLM 阶段跳过调用、
    改用规则兜底，保留已生成的图表与看板（已完成部分）。
    """

    WARN_RATIO = 0.80
    CUT_RATIO = 1.00

    def __init__(self, budget: int):
        self.budget = max(1, int(budget))
        self.used = 0
        self._warned = False
        self._cut = False

    def add(self, text: str = "") -> int:
        """累计一段文本的估算 token 消耗，返回本次增量。"""
        t = TokenManager.estimate_tokens(text or "")
        self.used += t
        return t

    @property
    def percent(self) -> float:
        return round(self.used / self.budget * 100, 1) if self.budget > 0 else 0.0

    def should_warn(self) -> bool:
        if not self._warned and self.percent >= self.WARN_RATIO * 100:
            self._warned = True
            return True
        return False

    def is_cut(self) -> bool:
        if not self._cut and self.used >= int(self.budget * self.CUT_RATIO):
            self._cut = True
        return self._cut


def _token_event(run_id: str, dataset_id: str, level: str, message: str, detail: Dict[str, Any]) -> str:
    """构造 token 预算相关 SSE 事件（token_warning / token_budget_exceeded）。

    level: "warn"（达 80% 告警） | "cut"（达 100% 熔断）。
    """
    data = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "event": "token_budget",
        "level": level,
        "used": detail.get("used"),
        "budget": detail.get("budget"),
        "percent": detail.get("percent"),
        "message": message,
        "detail": detail,
    }
    return f"event: token_budget\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _exec_skill(skill_id: str, ctx: SkillContext, fallback):
    """Phase 4：经注册 skill 执行某阶段；skill 不存在/抛错/返回 !ok 时回退到原内联逻辑。

    返回 skill 的 data（即内联代码原本拿到的对象），保证调用方零改造；
    fallback 为返回 awaitable 的协程（内联代码路径），行为与原管线完全一致。
    """
    try:
        skill = registry.get(skill_id)
        if skill is None:
            return await fallback()
        res = await skill.run(ctx)
        if res is None or not getattr(res, "ok", False):
            return await fallback()
        return res.data
    except Exception as e:  # skill 任何异常都不应中断生成，回退内联
        print(f"[Brain] skill {skill_id} 执行失败，回退内联逻辑: {e}")
        return await fallback()


async def get_dataset_info(db: AsyncSession, dataset_id: str) -> Dict[str, Any]:
    """从数据库获取数据集信息"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise ValueError(f"数据集不存在: {dataset_id}")
    
    fields = []
    column_types: Dict[str, str] = {}
    if dataset.schema_json and "columns" in dataset.schema_json:
        for col in dataset.schema_json["columns"]:
            _n = col.get("name", col.get("column"))
            if _n:
                fields.append(_n)
                column_types[_n] = str(col.get("type", "") or "").upper()
    
    # 从DuckDB获取样本数据
    db_duck = get_duckdb()
    table_name = f"ds_{dataset_id.replace('-', '_')}"
    sample_data = []
    if db_duck.table_exists(table_name):
        try:
            rows = db_duck.conn.execute(f'SELECT * FROM "{table_name}" LIMIT 5').fetchall()
            cols = [d[0] for d in db_duck.conn.execute(f'SELECT * FROM "{table_name}" LIMIT 0').description]
            sample_data = [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            print(f"[Brain] 获取样本数据失败: {e}")
    
    # 2026-09-17：派生指标反哺 S3 —— 先用真实数据反推跨列公式（如 抵押率 = 贷款金额 ÷ 抵押物评估价值），
    # 再交给图表引擎：让派生指标优先做指标、比率类禁止求和、图表配置带上加工口径。
    derived_metrics: Dict[str, Any] = {}
    try:
        from app.core.derived_metric_service import detect_derived_metrics, to_map
        cols = (dataset.schema_json or {}).get("columns") or []
        if cols and db_duck.table_exists(table_name):
            derived_metrics = to_map(
                detect_derived_metrics(db_duck, table_name, cols, max_rows=3000)
            )
            if derived_metrics:
                print("[Brain] 派生指标: " + "; ".join(
                    f"{k} = {v.get('expression', '')}({v.get('match_ratio', 0):.0%})"
                    for k, v in derived_metrics.items()
                ))
    except Exception as e:
        print(f"[Brain] 派生指标识别失败(不阻断): {e}")

    return {
        "dataset_id": dataset_id,
        "fields": fields,
        # 字段类型表（大写），供图表消毒层判断「度量列是否真为数值」
        "column_types": column_types,
        "grain": dataset.grain or "detail",
        "row_count": dataset.row_count,
        "theme_hint": dataset.profile_json.get("theme") if dataset.profile_json else None,
        "sample_data": sample_data,
        "dataset_name": dataset.name or "",
        "derived_metrics": derived_metrics,
    }


def _is_sensitive_field(f: str) -> bool:
    """2.5 P0 前置防御：敏感字段不注入取值样例（V4 红线前置），distinct 计数仍保留。"""
    return bool(re.search(r"(身份证|手机号|手机|电话|姓名|名称|地址|邮箱|邮件|证件|编号)", f or "", re.IGNORECASE))


def _compute_field_profiles(duck, table_name: str, fields: List[str],
                            sample_data: Optional[List[Dict]] = None) -> Optional[List[Dict[str, Any]]]:
    """S3 调用前算真实 distinct + 空值率（2.5 P0：L2 画像升级）。

    一次查询算所有字段的 COUNT(DISTINCT) 与空值数；失败返回 None，不阻断生成。
    列名来自数据集自有 schema（已校验），按白名单正则再过滤一次防注入。
    """
    if duck is None or not getattr(duck, "table_exists", lambda t: False)(table_name):
        return None
    safe = [f for f in fields if re.match(r"^[A-Za-z0-9_\u4e00-\u9fff]+$", f)]
    if not safe:
        return None
    try:
        parts = ["COUNT(*) AS _total"]
        for f in safe:
            q = '"' + f.replace('"', '""') + '"'
            parts.append(f"COUNT(DISTINCT {q})")
            parts.append(f"SUM(CASE WHEN {q} IS NULL THEN 1 ELSE 0 END)")
        row = duck.conn.execute(f'SELECT {", ".join(parts)} FROM "{table_name}"').fetchone()
        if not row:
            return None
        total = row[0] or 0
        profiles: List[Dict[str, Any]] = []
        idx = 1
        for f in safe:
            d = row[idx]
            n = row[idx + 1]
            idx += 2
            profiles.append({
                "name": f,
                "distinct_count": int(d) if d is not None else None,
                "null_rate": round(n / total, 4) if (total and n is not None) else 0.0,
            })
        # 取值样例：从 sample_data 取（敏感字段跳过，V4 前置防御）
        if sample_data:
            for p in profiles:
                if _is_sensitive_field(p["name"]):
                    continue
                vals: List[str] = []
                for r in sample_data:
                    v = r.get(p["name"])
                    if v is not None and str(v) not in vals:
                        vals.append(str(v))
                    if len(vals) >= 5:
                        break
                if vals:
                    p["sample_values"] = vals
        return profiles
    except Exception as e:
        print(f"[Brain] 字段画像计算失败(不阻断): {e}")
        return None


async def brain_run_pipeline(
    run_id: str,
    dataset_id: str,
    user_id: str
) -> AsyncGenerator[str, None]:
    """
    Brain运行管道 (接入真实大脑模块)
    
    五阶段：
    1. S1: 主题识别
    2. S2: 目标生成  
    3. S3: 图表推荐（LLM + Schema自愈）
    4. S4+S5: 编排优化+评分验证
    """
    
    async with async_session_factory() as db:
        progress = StageProgress(run_id, dataset_id)
        # P1-1 单任务 token 预算：按配置上限累计本次生成流水线各阶段 LLM 消耗
        budget = TokenBudget(getattr(settings, "BRAIN_TASK_TOKEN_BUDGET", 8000))
        token_cut = False  # 单任务预算熔断标志

        try:
            # 创建运行汇总记录（供 /status DB兜底恢复 & 服务重启后查询最终结果）
            await _safe_trace(db, BrainTraceManager.start_run(db, run_id, dataset_id, user_id), "start_run")

            # 获取数据集信息
            dataset_info = await get_dataset_info(db, dataset_id)

            # 数据六层落表（L1 norm / L2 cleaned / L4 agg 物化，best-effort 不阻断主流程）
            duck_inst = None
            try:
                duck_inst = get_duckdb()
                layers = duck_inst.materialize_layers(dataset_id)
                print(f"[Brain] 六层落表: {layers}")
            except Exception as e:
                print(f"[Brain] 六层落表失败(不阻断): {e}")

            # 八类数据质量探查（L2 清洗层，best-effort 不阻断）
            try:
                if duck_inst is not None:
                    from app.core.quality_checker import QualityChecker
                    cleaned_tbl = duck_inst.get_layer_table_name(dataset_id, "cleaned")
                    if not duck_inst.table_exists(cleaned_tbl):
                        cleaned_tbl = duck_inst.get_layer_table_name(dataset_id, "raw")
                    qcols = duck_inst.get_table_info(cleaned_tbl).get("columns", [])
                    qc = QualityChecker(duck_inst, None)
                    quality = qc.check_table(cleaned_tbl, qcols)
                    _RUN_STATUS.setdefault(run_id, {})["quality_summary"] = quality["summary"]
                    print(f"[Brain] 八类质量: {quality['summary']['by_type']}")
            except Exception as e:
                print(f"[Brain] 质量探查失败(不阻断): {e}")

            # 六层血缘自动构建（best-effort 不阻断）—— 数字可溯源
            try:
                from app.core.lineage_service import LineageService
                lineage = await LineageService.build_lineage_for_dataset(db, dataset_id)
                await LineageService.save_lineage_to_db(db, dataset_id, lineage)
                _RUN_STATUS.setdefault(run_id, {})["lineage_built"] = True
                print("[Brain] 血缘已构建并落库")
            except Exception as e:
                print(f"[Brain] 血缘构建失败(不阻断): {e}")
            fields = dataset_info["fields"]
            grain = dataset_info["grain"]
            sample_data = dataset_info["sample_data"]
            dataset_name = dataset_info["dataset_name"]
            derived_metrics = dataset_info.get("derived_metrics") or {}
            
            print(f"[Brain] 开始管道: dataset={dataset_id}, fields={fields}, grain={grain}")

            # ========== LLM 可达性探测（M1：失败则询问用户，不再静默规则） ==========
            # 原逻辑：探测失败→静默规则兜底（用户无感知）。现改为：探测失败→暂停并弹出选择框，
            # 让用户决定「立即规则兜底」或「等待 AI 恢复重试」。超时（BRAIN_AI_CHOICE_TIMEOUT）
            # 未操作则自动规则兜底，避免任务永久挂起。
            llm_offline = False
            try:
                llm_probe = await _check_llm_reachable()
                llm_offline = not llm_probe.get("reachable", False)
                if llm_offline:
                    # M1（拍板）：探针失败不再静默规则，改为询问用户（用户知情 + 用户选择）
                    print(f"[Brain] LLM 不可达({llm_probe.get('reason')})：暂停并询问用户")
                    choice = await _request_user_choice(run_id, {
                        "stage": "probe",
                        "options": ["rule_fallback", "wait_retry"],
                        "reason": llm_probe.get("reason") or "LLM 不可达",
                        "message": (
                            "AI 服务当前暂不可用（模型限流或超时）。\n"
                            "您可以：\n"
                            "· 用规则引擎立即生成基础看板（结果将标注「本次为规则生成」）\n"
                            "· 或等待 AI 恢复后重试"
                        ),
                    })
                    if choice == "wait_retry":
                        # 用户选择等待：重新探测一次；恢复则继续走 AI，否则仍走规则兜底
                        try:
                            _re = await _check_llm_reachable()
                            if _re.get("reachable"):
                                llm_offline = False
                                print("[Brain] 用户选择等待后重探测：AI 已恢复，继续走 LLM 路径")
                        except Exception:
                            pass
                    # 若 rule_fallback 或重探测仍不可达：保持 llm_offline=True → 后续阶段走规则兜底
            except Exception as e:
                # 探测本身异常：fail-closed 判为不可达，并询问用户（不再静默规则）
                print(f"[Brain] LLM 探测异常(按不可达处理并询问用户): {e}")
                llm_offline = True
                choice = await _request_user_choice(run_id, {
                    "stage": "probe",
                    "options": ["rule_fallback", "wait_retry"],
                    "reason": f"探测异常: {_short_err(e)}",
                    "message": "AI 服务探测异常（暂不可用）。您可改用规则引擎立即生成基础看板，或等待恢复后重试。",
                })
                if choice == "wait_retry":
                    try:
                        _re = await _check_llm_reachable()
                        if _re.get("reachable"):
                            llm_offline = False
                    except Exception:
                        pass

            # ========== Phase 4: 构建 SkillContext + 规划器（能力剪枝权威来源） ==========
            # planner 按 capability_profile 剪枝 LLM skill；这里 llm_offline 已是入口探测结果，
            # 与 registry.list_capable 一致，pipeline 据此驱动 S1/S2 经 skill 执行（内联兜底）。
            try:
                _planner = SkillPlanner(registry)
                _skill_plan = _planner.build("dashboard_generation", {"llm_reachable": not llm_offline})
                _RUN_STATUS.setdefault(run_id, {})["skill_plan"] = _skill_plan.order
            except Exception as _pe:
                print(f"[Brain] SkillPlanner 构建失败(忽略): {_pe}")
                _skill_plan = None
            ctx = SkillContext(
                db=db,
                duck=duck_inst,
                dataset_id=dataset_id,
                user_id=user_id,
                run_id=run_id,
                shared={
                    "fields": fields,
                    "sample_data": sample_data,
                    "grain": grain,
                    "derived_metrics": derived_metrics,
                    "dataset_name": dataset_name,
                },
                capability_profile={"llm_reachable": not llm_offline},
            )

            # ========== S1: 主题识别 ==========
            progress.current_stage = "S1"
            progress.stage_status = "running"
            progress.progress = 10
            progress.message = "正在分析数据主题..."
            yield progress.to_event()
            
            s1_trace_id = None
            theme_tag = "通用分析"  # 失败降级默认值
            try:
                s1_trace_id = await _safe_trace(db, BrainTraceManager.start_stage(db, run_id, dataset_id, "S1", {"fields": fields}), "S1")
                s1_result = await _exec_skill(
                    "understand:theme", ctx,
                    lambda: detect_theme(
                        db=db, fields=fields, sample_data=sample_data,
                        dataset_name=dataset_name, use_llm=not llm_offline,
                    ),
                )
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s1_trace_id, {"result": s1_result}), "S1")
                theme_tag = s1_result.get("theme_tag", "通用分析")
                # 兜底：主题识别为空或「未知」时统一用默认主题，避免看板标题显示「未知」
                if not theme_tag or theme_tag == "未知":
                    theme_tag = "数据概览"
                ctx.shared["theme"] = theme_tag
                progress.stage_status = "completed"
                progress.progress = 20
                progress.message = f"主题识别完成: {theme_tag}"
                progress.detail = s1_result
                yield progress.to_event()
                # P1-1 累计 S1 消耗并触发 80% 告警（仅一次）
                budget.add(json.dumps(s1_result, ensure_ascii=False))
                if budget.should_warn() and not token_cut:
                    yield _token_event(run_id, dataset_id, "warn",
                        f"本次生成 Token 已用 {budget.percent}%（预算 {budget.budget}），后续步骤将尽量精简。",
                        {"used": budget.used, "budget": budget.budget, "percent": budget.percent})
                print(f"[Brain] S1完成: {theme_tag}")
            except Exception as e:
                msg = f"第1步 主题识别失败：{_short_err(e)}。已使用默认主题继续后续分析，你可稍后重试或在对话中指定主题。"
                progress.stage_status = "failed"
                progress.message = msg
                _record_stage_error(run_id, "S1", msg)
                yield progress.to_event()
                print(f"[Brain] S1失败(降级继续): {e}")
            
            # ========== S2: 目标生成 ==========
            progress.current_stage = "S2"
            progress.stage_status = "running"
            progress.progress = 30
            progress.message = "正在生成分析目标..."
            yield progress.to_event()
            
            s2_trace_id = None
            goals = []  # 失败降级默认
            try:
                s2_trace_id = await _safe_trace(db, BrainTraceManager.start_stage(db, run_id, dataset_id, "S2", {
                    "theme": theme_tag, "fields": fields
                }), "S2")
                goals = await _exec_skill(
                    "understand:goal", ctx,
                    lambda: generate_analysis_goals(
                        db=db,
                        theme=theme_tag,
                        fields=fields,
                        grain=grain,
                        use_llm=bool(settings.BRAIN_S2_USE_LLM) and not llm_offline  # PRD 4.8：默认规则引擎降本，可开 LLM；与 skill 主路径(brain_skills.py:77)守卫一致
                    ),
                )
                ctx.shared["goals"] = goals
                # 2.3-B：标记 S2 目标生成是否由 LLM 参与（对齐 S3 的 ai_participated）
                s2_generated_by = "llm" if any(g.get("generated_by") == "llm" for g in goals) else "rule"
                ctx.shared["s2_generated_by"] = s2_generated_by
                # 3.2c：S2 一结束就能判定本次生成方式，提前写入状态缓存，
                # 让前端在 S3-S5（AI 阶段）加载中即可显示「AI 增强生成中 / 规则引擎生成中」，
                # 不必等到完成态。与最终 payload 的 generation_mode 同源。
                _RUN_STATUS.setdefault(run_id, {})["generation_mode"] = "ai" if s2_generated_by == "llm" else "rule"
                print(f"[Brain] S2 生成方式: {s2_generated_by}（{goals_count} 个目标）")
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s2_trace_id, {"goals": goals, "generated_by": s2_generated_by}), "S2")
                goals_count = len(goals)
                progress.stage_status = "completed"
                progress.progress = 40
                progress.message = f"生成{goals_count}个分析目标"
                progress.detail = {"goals": goals, "count": goals_count}
                yield progress.to_event()
                print(f"[Brain] S2完成: {goals_count}个目标")
            except Exception as e:
                msg = f"第2步 分析目标生成失败：{_short_err(e)}。已跳过目标生成，图表推荐将基于默认策略继续。"
                progress.stage_status = "failed"
                progress.message = msg
                _record_stage_error(run_id, "S2", msg)
                yield progress.to_event()
                print(f"[Brain] S2失败(降级继续): {e}")
            
            # ========== S3: 图表推荐（LLM + Schema自愈） ==========
            progress.current_stage = "S3"
            progress.stage_status = "running"
            progress.progress = 50
            progress.message = "正在推荐图表..."
            yield progress.to_event()
            
            s3_trace_id = None
            charts = []  # 失败降级默认
            generated_by = "rule_engine"
            s3_result = {"charts": [], "generated_by": "rule_engine"}
            s3_ai_failed = False
            s3_ai_reason = None
            # 2.5 P0：S3 调用前算真实字段画像（distinct/空值率/取值样例），喂给 LLM 出图决策
            _s3_table = f"ds_{dataset_id.replace('-', '_')}"
            field_profiles = _compute_field_profiles(
                get_duckdb(), _s3_table, fields, dataset_info.get("sample_data")
            )
            try:
                s3_trace_id = await _safe_trace(db, BrainTraceManager.start_stage(db, run_id, dataset_id, "S3", {
                    "theme": theme_tag, "fields": fields, "goals": goals
                }), "S3")
                if llm_offline:
                    # LLM 不可达：跳过 LLM 调用，直接走规则引擎兜底（省去 180s 超时等待）。
                    # 问题1修复：仍标记 s3_ai_failed，让用户在看板完成前被明确告知「AI 未参与」并可选择等待重试，
                    # 不再静默兜底（原设计因担心 600s 用户询问挂起而吞掉提示，导致生成看板时无限流告警）。
                    print("[Brain] LLM 不可达：S3 直接走规则引擎兜底，标记 s3_ai_failed 交还用户选择")
                    from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
                    engine = S3ChartEngine(derived_metrics=derived_metrics)
                    engine_cfg = engine.generate_dashboard_config(
                        fields=fields, grain=grain, derived_metrics=derived_metrics
                    )
                    s3_result = {
                        "charts": engine_cfg.get("charts", []),
                        "generated_by": "rule_engine",
                        "fallback_reason": "LLM 不可达，规则引擎兜底"
                    }
                    s3_ai_failed = True
                    s3_ai_reason = "AI 探测失败（模型限流/不可达），已用规则引擎兜底生成基础看板"
                else:
                    try:
                        s3_result = await asyncio.wait_for(
                            generate_charts_with_llm(
                                db=db,
                                theme=theme_tag,
                                fields=fields,
                                goals=goals,
                                grain=grain,
                                derived_metrics=derived_metrics,
                                field_profiles=field_profiles,
                            ),
                            timeout=settings.BRAIN_S3_LLM_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        # S3 LLM 调用在硬超时内未返回：规则引擎兜底。
                        # 问题1修复：标记 s3_ai_failed（不再仅靠 llm_offline 吞掉提示），
                        # 让用户在看板完成前被明确告知并可选「等待 AI 恢复重试」。
                        print(f"[Brain] S3 LLM 调用超时({settings.BRAIN_S3_LLM_TIMEOUT}s)，按规则引擎兜底，标记 s3_ai_failed")
                        from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
                        engine = S3ChartEngine(derived_metrics=derived_metrics)
                        engine_cfg = engine.generate_dashboard_config(
                            fields=fields, grain=grain, derived_metrics=derived_metrics
                        )
                        s3_result = {
                            "charts": engine_cfg.get("charts", []),
                            "generated_by": "rule_engine",
                            "fallback_reason": f"S3 LLM 调用超时({settings.BRAIN_S3_LLM_TIMEOUT}s)，规则引擎兜底",
                        }
                        s3_ai_failed = True
                        s3_ai_reason = f"S3 LLM 调用超时({settings.BRAIN_S3_LLM_TIMEOUT}s)，已用规则引擎兜底"
                        llm_offline = True
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s3_trace_id, {"result": s3_result}), "S3")
                # P1-1 累计 S3 消耗并触发 80% 告警（仅一次）
                budget.add(json.dumps(s3_result, ensure_ascii=False))
                if budget.should_warn() and not token_cut:
                    yield _token_event(run_id, dataset_id, "warn",
                        f"本次生成 Token 已用 {budget.percent}%（预算 {budget.budget}），后续步骤将尽量精简。",
                        {"used": budget.used, "budget": budget.budget, "percent": budget.percent})
                # 检测 AI 是否真正参与：generated_by != 'llm' 表示内部已降级到规则引擎
                # 注意：LLM 不可达时不计入「AI 失败」，以免触发 600s 用户询问挂起
                if not llm_offline and s3_result.get("generated_by") != "llm":
                    s3_ai_failed = True
                    s3_ai_reason = s3_result.get("fallback_reason") or "AI 图表生成调用失败"
            except Exception as e:
                s3_ai_failed = True
                s3_ai_reason = f"AI 图表生成异常: {_short_err(e)}"
                s3_result = {"charts": [], "generated_by": "rule_engine", "fallback_reason": s3_ai_reason}
                print(f"[Brain] S3失败(准备询问用户): {e}")

            # AI 失败：暂停流水线，把选择权交还用户（规则兜底生成 / 等 AI 恢复重试）
            # 问题1修复：任何 S3 AI 失败（含探针失败/超时导致的静默兜底）都弹出选择框，
            # 不再因 llm_offline 吞掉提示。用户选「等待重试」时由 _retry_s3_with_ai 重跑。
            if s3_ai_failed:
                choice = await _request_user_choice(run_id, {
                    "stage": "S3",
                    "options": ["rule_fallback", "wait_retry"],
                    "reason": s3_ai_reason,
                    "message": "图表推荐阶段的 AI 调用失败（模型限流或异常）。是否使用规则引擎兜底生成基础看板，还是等待 AI 恢复后重试？"
                })
                if choice == "wait_retry":
                    s3_result, s3_ai_failed = await _retry_s3_with_ai(
                        run_id, db, theme_tag, fields, goals, grain, s3_ai_reason,
                        derived_metrics=derived_metrics, field_profiles=field_profiles
                    )

            charts = s3_result.get("charts", [])
            generated_by = s3_result.get("generated_by", "rule_engine")
            # 若最终仍非 AI（规则兜底），确保 charts 存在；缺失则再兜底一次引擎默认
            if not charts:
                print("[Brain] S3图表为空（AI失败+规则兜底为空），回退到引擎默认图表")
                try:
                    from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
                    engine = S3ChartEngine(derived_metrics=derived_metrics)
                    default_cfg = engine.generate_dashboard_config(
                        fields=fields, grain=grain, derived_metrics=derived_metrics
                    )
                    charts = default_cfg.get("charts", [])
                    generated_by = "rule_engine_fallback"
                    s3_result["charts"] = charts
                    s3_result["generated_by"] = generated_by
                except Exception as fe:
                    print(f"[Brain] S3兜底也失败: {fe}")

            progress.stage_status = "completed" if charts else "failed"
            progress.progress = 60
            progress.message = f"推荐{len(charts)}个图表 ({generated_by})" + ("" if charts else "（无可用图表，请检查数据字段）")
            progress.detail = s3_result
            yield progress.to_event()
            
            print(f"[Brain] S3完成: {len(charts)}个图表, source={generated_by}")
            
            # ========== S4+S5: 编排优化+评分验证 ==========
            progress.current_stage = "S4"
            progress.stage_status = "running"
            progress.progress = 70
            progress.message = "正在编排优化看板..."
            yield progress.to_event()
            
            s4_trace_id = None
            s5_trace_id = None
            s4_s5_result = {"charts": charts, "overall_score": 0, "passed": False}
            try:
                s4_trace_id = await _safe_trace(db, BrainTraceManager.start_stage(db, run_id, dataset_id, "S4", {
                    "charts": charts
                }), "S4")
                s4_s5_result = await orchestrate_and_score(
                    db=db,
                    charts=charts,
                    dataset_id=dataset_id
                )
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s4_trace_id, {"result": s4_s5_result}), "S4")
            except Exception as e:
                msg = f"第4步 看板编排优化失败：{_short_err(e)}。已使用原始图表配置继续。"
                progress.current_stage = "S4"
                progress.stage_status = "failed"
                progress.message = msg
                _record_stage_error(run_id, "S4", msg)
                yield progress.to_event()
                print(f"[Brain] S4失败(降级继续): {e}")

            final_charts = s4_s5_result.get("charts", charts)
            overall_score = s4_s5_result.get("overall_score", 0)
            passed = s4_s5_result.get("passed", False)

            progress.current_stage = "S5"
            progress.stage_status = "running"
            progress.progress = 85
            progress.message = f"评分中: {overall_score}分"
            progress.detail = s4_s5_result
            yield progress.to_event()

            try:
                s5_trace_id = await _safe_trace(db, BrainTraceManager.start_stage(db, run_id, dataset_id, "S5", {
                    "score": overall_score,
                    "passed": passed,
                    "chart_count": len(charts)
                }), "S5")
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s5_trace_id, {"result": s4_s5_result}), "S5")
            except Exception as e:
                msg = f"第5步 评分验证失败：{_short_err(e)}。已跳过评分，看板照常生成。"
                progress.stage_status = "failed"
                progress.message = msg
                _record_stage_error(run_id, "S5", msg)
                yield progress.to_event()
                print(f"[Brain] S5失败(降级继续): {e}")

            # ========== S5 多模态视觉 5% 抽检 ==========
            try:
                from app.core.multimodal_sampler import MultimodalSampler
                duck_inst = get_duckdb()
                mm_charts = MultimodalSampler.sample_charts(final_charts)
                image_cols = MultimodalSampler.detect_image_columns(fields)
                mm_rows = MultimodalSampler.sample_rows_for_images(dataset_id, duck_inst, image_cols)
                s4_s5_result["multimodal_sampling"] = {
                    "charts": mm_charts,
                    "image_rows": mm_rows,
                }
                progress.detail = {
                    **(progress.detail or {}),
                    "multimodal_sampling": s4_s5_result["multimodal_sampling"],
                }
                # 写入状态缓存，供 /status 接口回传（与 detail 解耦，避免覆盖 DB 兜底中的 dashboard_id）
                _RUN_STATUS.setdefault(run_id, {})["multimodal_sampling"] = s4_s5_result["multimodal_sampling"]
                print(f"[Brain] S5多模态抽检(图): {mm_charts.get('report')} | (行): {mm_rows.get('report')}")
            except Exception as e:
                print(f"[Brain] S5多模态抽检失败(不阻断): {e}")

            progress.stage_status = "completed"
            progress.progress = 90
            progress.message = f"评分{'通过' if passed else '未通过'}: {overall_score}分"
            yield progress.to_event()
            
            print(f"[Brain] S4+S5完成: score={overall_score}, passed={passed}")

            # ========== S4b: LLM 生成分析说明文本（结论→佐证→建议） ==========
            progress.current_stage = "S4b"
            progress.stage_status = "running"
            progress.progress = 92
            progress.message = "正在生成分析说明..."
            yield progress.to_event()

            analysis_text = ""
            # P1-1 单任务 token 预算熔断：超预算则跳过 S4b 的 LLM 调用，保留已完成图表/看板
            if budget.is_cut():
                token_cut = True
                analysis_text = (
                    f"基于「{theme_tag}」主题，系统已自动生成 {len(final_charts)} 个分析图表。"
                    f"因单次生成 Token 预算（{budget.budget}）已用尽，分析说明改用规则摘要，"
                    f"如需更详细的业务解读可在右侧对话向 AI 追问。"
                )
                yield _token_event(run_id, dataset_id, "cut",
                    f"单次生成 Token 预算已用尽（{budget.percent}%），已保留已生成的 {len(final_charts)} 个图表并熔断后续 AI 调用。",
                    {"used": budget.used, "budget": budget.budget, "percent": budget.percent,
                     "completed_charts": len(final_charts), "theme": theme_tag})
                print(f"[Brain] 单任务 token 预算熔断，跳过 S4b LLM 调用")
            else:
                try:
                    from app.core.llm_gateway import llm_chat
                    from app.core.prompt_loader import load_prompt
    
                    charts_summary = ""
                    for i, c in enumerate(final_charts[:6], 1):
                        charts_summary += f"{i}. [{c.get('chart_type','?')}] {c.get('title','')} (维度: {c.get('x_field') or c.get('category_field','')} / 指标: {c.get('y_field') or c.get('value_field','')})\n"
    
                    goals_summary = "\n".join(f"- {g.get('goal','')}" for g in goals[:5]) if goals else "无"
    
                    # ★ 改造：分析说明按原型升级为「结论 → 佐证 → 建议」完整段落，
                    # 解决用户反馈"按原型除了图表还有分析报告"。
                    # 长度从 200 字提升到 400-700 字，含 3 段：
                    # ① 业务结论（核心数据发现 + 趋势）
                    # ② 归因/佐证（关键图表数据指向）
                    # ③ actionable 建议（2-3 条具体动作）
                    prompt_text = (
                        f"你是一位资深 BI 数据分析师。请基于以下看板数据，撰写一段「分析报告」正文，"
                        f"用于在 AI 生成的看板顶部作为「AI 分析摘要」展示。\n\n"
                        f"## 看板主题\n{theme_tag}\n\n"
                        f"## 分析目标\n{goals_summary}\n\n"
                        f"## 图表配置\n{charts_summary}\n\n"
                        f"## 撰写要求（务必遵循）\n"
                        f"1. 总长度 400-700 字；分 3 段（结论 → 佐证 → 建议），中间用换行分隔，不要列表。\n"
                        f"2. 第一段【结论】：用 2-3 句话概括核心业务发现，必须包含关键数字或比例（基于上述图表配置合理推断即可）。\n"
                        f"3. 第二段【佐证】：用 2-3 句话把结论归因到具体图表维度，例如「结合『XX 分布』与『YY 趋势』可见……」。\n"
                        f"4. 第三段【建议】：给出 2-3 条 actionable 业务动作建议，例如「建议收紧 X 类准入」「加强对 Y 维度的监控」等。\n"
                        f"5. 用专业但平实的 BI 分析师口吻；中文输出；不要 JSON；不要 Markdown 加粗；"
                        f"不要使用 emoji；避免『综上所述』『值得关注』等空话。\n\n"
                        f"分析报告正文："
                    )
                    system_prompt = load_prompt(
                        "ai_assistant_spec",
                        "你是一位资深 BI 数据分析师，擅长用业务语言解读图表数据，输出结论—佐证—建议三段式分析报告。"
                    )
                    # P1-1 累计本次 prompt 消耗
                    budget.add(system_prompt + "\n\n" + prompt_text)
                    # 若仅本次 prompt 就把预算推过线，则熔断，保留已生成图表
                    if budget.is_cut():
                        token_cut = True
                        analysis_text = (
                            f"基于「{theme_tag}」主题，系统已自动生成 {len(final_charts)} 个分析图表。"
                            f"因单次生成 Token 预算（{budget.budget}）已用尽，分析说明改用规则摘要，"
                            f"如需更详细的业务解读可在右侧对话向 AI 追问。"
                        )
                        yield _token_event(run_id, dataset_id, "cut",
                            f"单次生成 Token 预算已用尽（{budget.percent}%），已保留已生成的 {len(final_charts)} 个图表并熔断后续 AI 调用。",
                            {"used": budget.used, "budget": budget.budget, "percent": budget.percent,
                             "completed_charts": len(final_charts), "theme": theme_tag})
                        print(f"[Brain] 单任务 token 预算在 S4b 估算后熔断，跳过 LLM 调用")
                    else:
                        llm_resp = await llm_chat(
                            prompt=system_prompt + "\n\n" + prompt_text,
                            json_mode=False,
                            user_id="analysis_text",
                            timeout=60,  # 分析说明：超时则回退到系统基于真实统计生成的文案
                        )
                        if llm_resp.success and llm_resp.content:
                            analysis_text = llm_resp.content.strip()
                            budget.add(analysis_text)  # 累计 completion 消耗
                        else:
                            analysis_text = (
                                f"基于「{theme_tag}」主题，系统已自动生成 {len(final_charts)} 个分析图表，"
                                f"覆盖核心业务维度与关键指标。建议结合各图表交叉解读重点趋势，"
                                f"对异常占比与连续下行指标安排后续复核与跟进。"
                            )
                except Exception as e:
                    print(f"[Brain] 分析文本生成失败（不影响看板生成）: {e}")
                    analysis_text = (
                        f"基于「{theme_tag}」主题，系统已自动生成 {len(final_charts)} 个分析图表。"
                        f"如需更详细的业务解读，可在右侧对话中向 AI 追问。"
                    )

            progress.stage_status = "completed"
            yield progress.to_event()
            print(f"[Brain] S4b完成: analysis_text_len={len(analysis_text)}")

            # ========== 保存看板到数据库 ==========
            dashboard_id = f"dash_{dataset_id[:8]}_{uuid.uuid4().hex[:6]}"

            # ========== 图表消毒（落库前最后一道闸门） ==========
            try:
                _ct = {}
                if isinstance(dataset_info, dict):
                    _ct = dataset_info.get("column_types") or {}
                # 计算维度字段基数（去重计数），用于过滤单值维度图表
                _card: Dict[str, int] = {}
                if duck_inst is not None and final_charts:
                    _tbl = duck_inst.get_layer_table_name(dataset_id, "cleaned")
                    if not duck_inst.table_exists(_tbl):
                        _tbl = duck_inst.get_layer_table_name(dataset_id, "raw")
                    _valid = set(fields or [])
                    _qt = f'"{_tbl}"'
                    _dims = []
                    for _c in final_charts:
                        if isinstance(_c, dict):
                            _d = _c.get("x_field") or _c.get("category_field")
                            if _d and _d in _valid and _d not in _dims:
                                _dims.append(_d)
                    for _d in _dims:
                        try:
                            _r = duck_inst.conn.execute(
                                f'SELECT COUNT(DISTINCT "{_d}") FROM {_qt}'
                            ).fetchone()
                            _card[_d] = int(_r[0]) if _r and _r[0] is not None else 0
                        except Exception:
                            pass
                final_charts = _sanitize_charts(final_charts, fields, _ct, _card)
            except Exception as se:
                print(f"[Brain] 图表消毒异常(不阻断): {se}")
            
            # 构建看板配置
            # 2026-09-17 修复：为每张图表写入来源 dataset_id。
            # 多文件场景下 a 数据生成图表1/2/3、b 数据生成图表4/5/6，合并进同一看板后，
            # 前端必须按各自来源数据集取数，否则跨数据集图表（字段只存在于另一份表）全部空图。
            for _c in final_charts:
                if isinstance(_c, dict) and not _c.get("dataset_id"):
                    _c["dataset_id"] = dataset_id
                # 派生指标兜底：S3 已注入，这里再补一层，确保任何生成路径落库都带加工口径
                if isinstance(_c, dict) and derived_metrics:
                    _m = _c.get("y_field") or _c.get("value_field")
                    if _m and _m in derived_metrics and not (_c.get("config") or {}).get("derived_metric"):
                        _info = derived_metrics[_m]
                        try:
                            from app.core.derived_metric_service import recommended_agg, is_ratio_metric
                            _agg = recommended_agg(_info)
                            _ratio = is_ratio_metric(_info)
                        except Exception:
                            _agg, _ratio = "avg", True
                        _cfg = _c.get("config")
                        if not isinstance(_cfg, dict):
                            _cfg = {}
                            _c["config"] = _cfg
                        _cfg["aggregation"] = _agg
                        _cfg["derived_metric"] = {
                            "metric": _m,
                            "formula": _info.get("formula", ""),
                            "expression": _info.get("expression", ""),
                            "components": _info.get("components", []),
                            "match_ratio": _info.get("match_ratio", 0),
                            "aggregation": _agg,
                            "ratio": _ratio,
                        }

            # 2.3-B：合并 S2(目标) 与 S3(图表) 的 AI 参与情况
            s2_gen = ctx.shared.get("s2_generated_by", "rule")
            ai_participated = (generated_by == "llm") or (s2_gen == "llm")
            dashboard_config = {
                "charts": final_charts,
                "chart_count": len(final_charts),
                "theme": theme_tag,
                "goals": goals,
                "generated_by": generated_by,
                # 2.3-B：S2 目标生成的 AI 参与标记（对齐 S3），路演可证明"目标生成也由 AI 参与"
                "s2_generated_by": s2_gen,
                # 问题1修复（Layer2）：把生成方式显式落库，供前端打开看板时渲染绿标/灰标
                # （此前仅在 SSE 完成事件 detail 里算，未写入 config，导致打开页无标注）
                # 2.3-B：ai_participated 合并 S2(目标) 与 S3(图表)，任一为 LLM 即 True
                "ai_participated": ai_participated,
                "generation_mode": "ai" if ai_participated else "rule",
                "score": {
                    "overall": overall_score,
                    "passed": passed,
                    "dimensions": s4_s5_result.get("dimension_scores", {})
                },
                "analysis_text": analysis_text,
                # 派生指标（已用真实数据反推验证的加工公式），血缘/前端据此白盒展示指标口径
                "derived_metrics": derived_metrics,
                # #7 修复：0 可视化字段时把 PRD 引导建议一并落库，前端空看板可展示
                "no_chartable_fields": s3_result.get("no_chartable_fields", False),
                "suggestion": s3_result.get("suggestion", "")
            }
            
            # 保存Dashboard记录
            dash = Dashboard(
                id=dashboard_id,
                name=f"{dataset_name}看板",
                description=f"基于{theme_tag}主题的自动分析看板",
                status="published",
                score=overall_score,
                passed=passed,
                dataset_ids=[dataset_id],
                primary_dataset_id=dataset_id,
                config=dashboard_config,
                layout={"narrative": s4_s5_result.get("narrative_flow", ""), "chart_count": len(final_charts)},
                created_by=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(dash)
            await db.commit()

            # C04 版本管理：看板生成完成后自动落一个初始版本快照（用户可在「版本管理」回退）
            try:
                await VersionManager.create_version(
                    db, dashboard_id,
                    name="AI生成初始版本",
                    description="系统自动保存：AI首次生成看板",
                    created_by=user_id,
                    is_auto_save=True,
                )
            except Exception as ve:
                print(f"[Brain] 自动版本快照失败(忽略): {ve}")

            await _safe_trace(
                db, BrainTraceManager.complete_run(
                    db, run_id,
                    dashboard_id=dashboard_id,
                    final_score=int(overall_score),
                    passed=passed
                ),
                "complete_run"
            )
            
            # ========== 完成 ==========
            progress.current_stage = "COMPLETE"
            progress.stage_status = "completed"
            progress.progress = 100
            progress.message = "看板生成完成！"
            progress.detail = {
                "dashboard_id": dashboard_id,
                "chart_count": len(final_charts),
                "final_score": overall_score,
                "passed": passed,
                "theme": theme_tag,
                # Phase 4 透明度：前端据此区分「AI 参与」与「规则兜底」，避免「模型不可用却显示成功」
                "generated_by": generated_by,
                # 2.3-B：S2 目标生成的 AI 参与标记（与 dashboard_config 一致）
                "s2_generated_by": s2_gen,
                "ai_participated": ai_participated,
                # M2（拍板）：显式标注生成方式，供前端展示「本次为规则生成」徽标
                "generation_mode": "ai" if ai_participated else "rule",
                "no_chartable_fields": s3_result.get("no_chartable_fields", False),
                "suggestion": s3_result.get("suggestion", "")
            }
            yield progress.to_event()
            
            print(f"[Brain] 完成: dashboard_id={dashboard_id}, charts={len(final_charts)}")
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[Brain] 管道失败: {e}\n{error_detail}")

            progress.stage_status = "failed"
            # 精简为可读单行，避免把LLM超时等嵌套异常直接堆给用户
            raw = str(e) if e else "未知异常"
            reason = raw.strip().splitlines()[0][:200] if raw.strip() else "未知异常"
            stage_errors = _RUN_STATUS.get(run_id, {}).get("stage_errors", {})
            if stage_errors:
                failed_steps = "；".join(f"{k}步（{v.split('。')[0]}）" for k, v in stage_errors.items())
                msg = f"分析管道已完成，但存在失败步骤：{failed_steps}。可重试运行，或在对话中调整数据/字段后重新生成。"
            else:
                msg = f"分析管道执行失败：{reason}。请稍后重试；若持续失败，请检查数据集或联系管理员。"
            progress.message = msg
            progress.detail = {"error": raw, "stage_errors": stage_errors}
            _RUN_STATUS.setdefault(run_id, {})["stage_errors"] = stage_errors
            yield progress.to_event()


async def check_blocking_issues(db: AsyncSession, dataset_id: str) -> tuple[bool, list]:
    """
    M1-10 二次质检门禁：检查必拦项是否全部处理
    """
    from sqlalchemy import select, and_
    
    result = await db.execute(
        select(QualityIssue).where(
            and_(
                QualityIssue.dataset_id == dataset_id,
                QualityIssue.severity == "blocking",
                QualityIssue.status.in_(["pending", "confirmed"])
            )
        )
    )
    blocking_issues = result.scalars().all()
    
    if not blocking_issues:
        return True, []
    
    issues_list = [
        {
            "id": iss.id,
            "issue_type": iss.type,
            "field": iss.field_name,
            "message": iss.message
        }
        for iss in blocking_issues
    ]
    return False, issues_list


@router.post("/run")
async def brain_run(
    request: BrainRunRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    启动策略大脑（后台任务，立即返回run_id）

    M1-10 二次质检门禁：必拦未清零 → 返回403

    任务在服务端后台执行，独立于请求生命周期：
    - 前端可 POST /brain/run/{run_id}/cancel 取消
    - 前端可 GET /brain/run/{run_id}/status 随时查询进度与最终结果
    - 即使离开页面，任务继续运行，返回后可查看结果

    D2-4 修复：需登录。D2-1 修复：看板 owner 取服务端登录身份（current_user["user_id"]），
    不再信任客户端 request.user_id。
    """
    uid = current_user["user_id"]
    run_id = str(uuid.uuid4())
    
    async with async_session_factory() as db:
        passed, blocking_issues = await check_blocking_issues(db, request.dataset_id)
        if not passed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "QUALITY_GATE_BLOCKED",
                    "message": f"存在 {len(blocking_issues)} 个未处理的必拦问题",
                    "blocking_issues": blocking_issues,
                    "resolution": "请先修复数据质量问题后再运行策略大脑"
                }
            )
    
    # 2026-09-18 幂等护栏：同一数据集已有运行中的生成任务时，直接复用该 run。
    # 此前前端 React.StrictMode 双挂载/快速双击会对同一数据集连发两次 /brain/run，
    # 生成两个一模一样的看板（"我的看板"列表出现重复）。
    for _rid, _st in _RUN_STATUS.items():
        if (
            _st.get("dataset_id") == request.dataset_id
            and _st.get("status") in ("running", "starting")
            and _rid in _RUN_TASKS and not _RUN_TASKS[_rid].done()
        ):
            return {
                "success": True,
                "run_id": _rid,
                "status": "started",
                "reused": True,
                "message": "该数据集已有生成任务进行中，已复用现有任务",
                "status_url": f"/api/v1/brain/run/{_rid}/status"
            }

    _RUN_STATUS[run_id] = {"status": "running", "progress": 0, "message": "任务已启动", "dataset_id": request.dataset_id}
    task = asyncio.create_task(_run_worker(run_id, request.dataset_id, uid))
    _RUN_TASKS[run_id] = task

    return {
        "success": True,
        "run_id": run_id,
        "status": "started",
        "status_url": f"/api/v1/brain/run/{run_id}/status"
    }


@router.get("/run/{run_id}/status")
async def get_run_status(
    run_id: str,
    dataset_id: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)
):
    """
    查询运行状态（可随时调用，任务无关乎前端是否在页面）

    status: running / completed / failed / cancelled / unknown
    completed 时 detail 含 dashboard_id，可直接跳转看板

    新增 dataset_id 参数：当 run 不在内存/DB 也找不到时，自动反查该 dataset
    最近一份 published 看板，有则返回 completed（解决"后端重启后 LoadingPage
    误报『未找到该后台任务』、但其实看板早已落库"的体验断裂）。
    """
    cache = _RUN_STATUS.get(run_id)
    if cache:
        return {
            "success": True,
            "run_id": run_id,
            "status": cache.get("status", "running"),
            "stage": cache.get("stage", ""),
            "progress": cache.get("progress", 0),
            "message": cache.get("message", ""),
            "detail": cache.get("detail") or {},
            "multimodal_sampling": cache.get("multimodal_sampling"),
            "quality_summary": cache.get("quality_summary"),
            "lineage_built": cache.get("lineage_built", False),
            "stage_errors": cache.get("stage_errors") or {},
            "ai_awaiting": cache.get("ai_awaiting"),
            "generation_mode": cache.get("generation_mode"),
            "finished": cache.get("finished", False)
        }
    # 兜底：从DB读取（服务重启后查询已持久化的运行痕迹）
    summary = None
    try:
        async with async_session_factory() as db:
            summary = await BrainTraceManager.get_run_summary(db, run_id)
            if summary:
                overall = summary.get("status") or summary.get("overall_status") or "unknown"
                # ★ 关键修复：summary 显示 running 但 updated_at 距今超过 3 分钟
                # → 视为"任务已中断"（后端崩溃/被 kill/重启）。
                # 此时前端不必再轮询，应降级为"未找到"并提示用户重新生成。
                last_update_raw = summary.get("updated_at") or summary.get("updatedAt")
                stale = False
                if overall == "running" and last_update_raw:
                    try:
                        last_dt = last_update_raw if isinstance(last_update_raw, datetime) else datetime.fromisoformat(str(last_update_raw))
                        stale = (datetime.now() - last_dt).total_seconds() > 180  # 3 分钟
                    except Exception:
                        stale = False
                if stale:
                    return {
                        "success": True,
                        "run_id": run_id,
                        "status": "unknown",
                        "stage": summary.get("current_stage", ""),
                        "progress": summary.get("progress", 0),
                        "message": "任务已被服务端清理（可能因重启或进程中断），请重新生成",
                        "detail": {"interrupted": True, "stale_seconds": True},
                        "finished": True,
                    }
                return {
                    "success": True,
                    "run_id": run_id,
                    "status": overall if overall != "unknown" else "running",
                    "stage": summary.get("current_stage", ""),
                    "progress": summary.get("progress", 0),
                    "message": summary.get("message", ""),
                    "detail": {},
                    "finished": overall in ("completed", "failed", "cancelled")
                }
    except Exception:
        pass

    # 兜底2：summary丢失时，按 run_id→brain_traces→dataset→已落库看板 反查
    # 解决“看板已成功生成但仍显示空/失败、重新提交死循环”的问题
    if not summary:
        try:
            async with async_session_factory() as db:
                tr = await db.execute(
                    select(BrainTrace).where(BrainTrace.run_id == run_id).order_by(BrainTrace.created_at)
                )
                traces = tr.scalars().all()
                if traces:
                    ds_id = traces[0].dataset_id
                    latest_stage = traces[-1].stage
                    failed_trace = next((t for t in traces if t.stage_status == "failed"), None)
                    dash = await db.execute(
                        select(Dashboard)
                        .where(Dashboard.primary_dataset_id == ds_id, Dashboard.status == "published")
                        .order_by(Dashboard.created_at.desc())
                    )
                    d = dash.scalars().first()
                    if failed_trace:
                        return {
                            "success": True, "run_id": run_id,
                            "status": "failed",
                            "stage": failed_trace.stage,
                            "progress": 90,
                            "message": f"处理失败: {failed_trace.error_info or '阶段异常'}",
                            "detail": {"error": str(failed_trace.error_info)},
                            "finished": True
                        }
                    if d:
                        cfg = d.config or {}
                        cc = cfg.get("chart_count", 0) if isinstance(cfg, dict) else 0
                        return {
                            "success": True, "run_id": run_id,
                            "status": "completed",
                            "stage": "COMPLETE",
                            "progress": 100,
                            "message": "看板生成完成！",
                            "detail": {"dashboard_id": d.id, "chart_count": cc, "final_score": d.score},
                            "finished": True
                        }
                    return {
                        "success": True, "run_id": run_id,
                        "status": "running",
                        "stage": latest_stage,
                        "progress": 90,
                        "message": f"已到达 {latest_stage}: 看板尚未落库，请稍后刷新",
                        "detail": {},
                        "finished": False
                    }
        except Exception:
            pass

    # 兜底3：run_id 完全查不到（前端可能是 stale localStorage 或后端重启太彻底），
    # 但前端若带了 dataset_id，则按 dataset 反查最近一份 published 看板，
    # 只要存在就返回 completed（实现"任务早已成功但用户没及时看到"的自动恢复）。
    if dataset_id:
        try:
            async with async_session_factory() as db:
                dash = await db.execute(
                    select(Dashboard)
                    .where(Dashboard.primary_dataset_id == dataset_id, Dashboard.status == "published")
                    .order_by(Dashboard.created_at.desc())
                )
                d = dash.scalars().first()
                if d:
                    cfg = d.config or {}
                    cc = cfg.get("chart_count", 0) if isinstance(cfg, dict) else 0
                    return {
                        "success": True, "run_id": run_id,
                        "status": "completed",
                        "stage": "COMPLETE",
                        "progress": 100,
                        "message": "看板生成完成！（服务端已自动恢复）",
                        "detail": {
                            "dashboard_id": d.id,
                            "chart_count": cc,
                            "final_score": d.score,
                            "recovered_by_dataset": True,
                        },
                        "finished": True,
                    }
        except Exception:
            pass

    return {
        "success": True,
        "run_id": run_id,
        "status": "unknown",
        "progress": 0,
        "detail": {"interrupted": True}
    }


@router.post("/run/{run_id}/cancel")
async def cancel_run(run_id: str, current_user: Dict = Depends(get_current_user)):
    """取消后台运行任务"""
    task = _RUN_TASKS.get(run_id)
    if task and not task.done():
        task.cancel()
        _RUN_STATUS[run_id]["status"] = "cancelled"
        _RUN_STATUS[run_id]["message"] = "任务已被取消"
    elif run_id in _RUN_STATUS and _RUN_STATUS[run_id].get("status") == "running":
        _RUN_STATUS[run_id]["status"] = "cancelled"
        _RUN_STATUS[run_id]["message"] = "任务已被取消"
    return {
        "success": True,
        "run_id": run_id,
        "message": "取消请求已发送"
    }


class ResumeRunRequest(BaseModel):
    """用户针对 AI 失败暂停的抉择回传"""
    choice: str = Field(..., description="'rule_fallback'=规则兜底生成 / 'wait_retry'=等 AI 恢复重试")


@router.post("/run/{run_id}/resume")
async def resume_run(run_id: str, body: ResumeRunRequest, current_user: Dict = Depends(get_current_user)):
    """AI 失败暂停时，用户回传选择（规则兜底 / 等恢复重试），唤醒流水线继续。"""
    if body.choice not in ("rule_fallback", "wait_retry"):
        raise HTTPException(status_code=400, detail={"error": "BAD_CHOICE", "message": "choice 必须为 rule_fallback 或 wait_retry"})
    awakened = _resume_run_choice(run_id, body.choice)
    if not awakened:
        # 流水线可能已结束或早已继续（如超时自动兜底），回传当前状态由前端判断
        return {
            "success": True,
            "run_id": run_id,
            "awakened": False,
            "message": "未找到等待中的流水线（可能已超时自动继续），请刷新状态查看"
        }
    return {
        "success": True,
        "run_id": run_id,
        "awakened": True,
        "choice": body.choice,
        "message": "已收到您的选择，流水线继续"
    }