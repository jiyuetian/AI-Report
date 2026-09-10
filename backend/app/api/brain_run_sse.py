"""
/brain/run SSE - M2-08 (R1返工: 接入真实大脑)
五阶段进度流式回传（对应Loading页五阶段）
"""
import asyncio
import json
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from app.core.database import async_session_factory
from app.core.brain_config_manager import BrainTraceManager
from app.core.duckdb_manager import get_duckdb
from app.core.config import settings
from app.core.brain_modules import (
    detect_theme, generate_analysis_goals, generate_charts_with_llm,
    orchestrate_and_score
)
from app.models.dataset import Dataset
from app.models.dashboard import Dashboard
from app.models.quality import QualityIssue
from app.models.brain import BrainTrace, BrainTraceSummary

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


def _record_stage_error(run_id: str, stage: str, msg: str) -> None:
    """记录某阶段用户可读的失败消息，供 /status 回传，避免用户只看到笼统报错"""
    _RUN_STATUS.setdefault(run_id, {}).setdefault("stage_errors", {})[stage] = msg


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


async def get_dataset_info(db: AsyncSession, dataset_id: str) -> Dict[str, Any]:
    """从数据库获取数据集信息"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise ValueError(f"数据集不存在: {dataset_id}")
    
    fields = []
    if dataset.schema_json and "columns" in dataset.schema_json:
        fields = [col.get("name", col.get("column")) for col in dataset.schema_json["columns"]]
    
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
    
    return {
        "dataset_id": dataset_id,
        "fields": fields,
        "grain": dataset.grain or "detail",
        "row_count": dataset.row_count,
        "theme_hint": dataset.profile_json.get("theme") if dataset.profile_json else None,
        "sample_data": sample_data,
        "dataset_name": dataset.name or ""
    }


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
            
            print(f"[Brain] 开始管道: dataset={dataset_id}, fields={fields}, grain={grain}")
            
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
                s1_result = await detect_theme(
                    db=db,
                    fields=fields,
                    sample_data=sample_data,
                    dataset_name=dataset_name
                )
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s1_trace_id, {"result": s1_result}), "S1")
                theme_tag = s1_result.get("theme_tag", "通用分析")
                progress.stage_status = "completed"
                progress.progress = 20
                progress.message = f"主题识别完成: {theme_tag}"
                progress.detail = s1_result
                yield progress.to_event()
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
                goals = await generate_analysis_goals(
                    db=db,
                    theme=theme_tag,
                    fields=fields,
                    grain=grain,
                    use_llm=settings.BRAIN_S2_USE_LLM  # PRD 4.8：默认规则引擎降本，可开 LLM
                )
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s2_trace_id, {"goals": goals}), "S2")
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
            try:
                s3_trace_id = await _safe_trace(db, BrainTraceManager.start_stage(db, run_id, dataset_id, "S3", {
                    "theme": theme_tag, "fields": fields, "goals": goals
                }), "S3")
                s3_result = await generate_charts_with_llm(
                    db=db,
                    theme=theme_tag,
                    fields=fields,
                    goals=goals,
                    grain=grain
                )
                await _safe_trace(db, BrainTraceManager.complete_stage(db, s3_trace_id, {"result": s3_result}), "S3")
                charts = s3_result.get("charts", [])
                generated_by = s3_result.get("generated_by", "rule_engine")
            except Exception as e:
                msg = f"第3步 图表推荐失败：{_short_err(e)}。将回退到内置规则引擎重新生成图表。"
                progress.stage_status = "failed"
                progress.message = msg
                _record_stage_error(run_id, "S3", msg)
                print(f"[Brain] S3失败(尝试规则引擎回退): {e}")
            # 容错：若LLM限流/异常导致图表为空，回退到引擎默认配置，保证看板仍能生成
            if not charts:
                print("[Brain] S3图表为空（可能LLM限流/异常），回退到引擎默认图表")
                try:
                    from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
                    engine = S3ChartEngine()
                    default_cfg = engine.generate_dashboard_config(fields=fields, grain=grain)
                    charts = default_cfg.get("charts", [])
                    generated_by = "rule_engine_fallback"
                    s3_result["charts"] = charts
                    s3_result["generated_by"] = generated_by
                    if charts:
                        progress.stage_status = "completed"
                except Exception as fe:
                    print(f"[Brain] S3兜底也失败: {fe}")
            if progress.stage_status != "completed":
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
            try:
                from app.core.llm_gateway import llm_chat
                from app.core.prompt_loader import load_prompt

                charts_summary = ""
                for i, c in enumerate(final_charts[:6], 1):
                    charts_summary += f"{i}. [{c.get('chart_type','?')}] {c.get('title','')} (维度: {c.get('x_field') or c.get('category_field','')} / 指标: {c.get('y_field') or c.get('value_field','')})\n"

                goals_summary = "\n".join(f"- {g.get('goal','')}" for g in goals[:5]) if goals else "无"

                prompt_text = (
                    f"你是一位资深数据分析师。请为以下看板生成一段简短的分析说明（200字以内）。\n\n"
                    f"## 看板主题\n{theme_tag}\n\n"
                    f"## 分析目标\n{goals_summary}\n\n"
                    f"## 图表配置\n{charts_summary}\n\n"
                    f"## 要求\n"
                    f"1. 用3-5句话概括核心发现\n"
                    f"2. 说明数据反映的业务含义\n"
                    f"3. 给出1-2条 actionable 建议\n"
                    f"4. 中文输出，不要JSON\n\n"
                    f"分析说明："
                )
                system_prompt = load_prompt(
                    "ai_assistant_spec",
                    "你是一位资深 BI 数据分析师。"
                )
                llm_resp = await llm_chat(
                    prompt=system_prompt + "\n\n" + prompt_text,
                    json_mode=False,
                    user_id="analysis_text"
                )
                if llm_resp.success and llm_resp.content:
                    analysis_text = llm_resp.content.strip()
                else:
                    analysis_text = f"基于「{theme_tag}」主题，系统已自动生成{len(final_charts)}个分析图表，覆盖核心业务维度和关键指标。"
            except Exception as e:
                print(f"[Brain] 分析文本生成失败（不影响看板生成）: {e}")
                analysis_text = f"基于「{theme_tag}」主题，系统已自动生成{len(final_charts)}个分析图表。"

            progress.stage_status = "completed"
            yield progress.to_event()
            print(f"[Brain] S4b完成: analysis_text_len={len(analysis_text)}")

            # ========== 保存看板到数据库 ==========
            dashboard_id = f"dash_{dataset_id[:8]}_{uuid.uuid4().hex[:6]}"
            
            # 构建看板配置
            dashboard_config = {
                "charts": final_charts,
                "chart_count": len(final_charts),
                "theme": theme_tag,
                "goals": goals,
                "generated_by": generated_by,
                "score": {
                    "overall": overall_score,
                    "passed": passed,
                    "dimensions": s4_s5_result.get("dimension_scores", {})
                },
                "analysis_text": analysis_text,
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
async def brain_run(request: BrainRunRequest):
    """
    启动策略大脑（后台任务，立即返回run_id）
    
    M1-10 二次质检门禁：必拦未清零 → 返回403
    
    任务在服务端后台执行，独立于请求生命周期：
    - 前端可 POST /brain/run/{run_id}/cancel 取消
    - 前端可 GET /brain/run/{run_id}/status 随时查询进度与最终结果
    - 即使离开页面，任务继续运行，返回后可查看结果
    """
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
    
    _RUN_STATUS[run_id] = {"status": "running", "progress": 0, "message": "任务已启动"}
    task = asyncio.create_task(_run_worker(run_id, request.dataset_id, request.user_id))
    _RUN_TASKS[run_id] = task

    return {
        "success": True,
        "run_id": run_id,
        "status": "started",
        "status_url": f"/api/v1/brain/run/{run_id}/status"
    }


@router.get("/run/{run_id}/status")
async def get_run_status(run_id: str):
    """
    查询运行状态（可随时调用，任务无关乎前端是否在页面）
    
    status: running / completed / failed / cancelled / unknown
    completed 时 detail 含 dashboard_id，可直接跳转看板
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
            "finished": cache.get("finished", False)
        }
    # 兜底：从DB读取（服务重启后查询已持久化的运行痕迹）
    summary = None
    try:
        async with async_session_factory() as db:
            summary = await BrainTraceManager.get_run_summary(db, run_id)
            if summary:
                return {
                    "success": True,
                    "run_id": run_id,
                    "status": summary.get("status", "unknown"),
                    "stage": summary.get("current_stage", ""),
                    "progress": summary.get("progress", 0),
                    "message": summary.get("message", ""),
                    "detail": {},
                    "finished": summary.get("status") in ("completed", "failed", "cancelled", "unknown")
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

    return {
        "success": True,
        "run_id": run_id,
        "status": "unknown",
        "progress": 0,
        "detail": {}
    }


@router.post("/run/{run_id}/cancel")
async def cancel_run(run_id: str):
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