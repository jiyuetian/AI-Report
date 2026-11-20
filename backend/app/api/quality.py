"""质检API - M1-08a/b 六类质检 + AI补充检测 + 清洗层写入"""
import time
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, or_
from pydantic import BaseModel

from app.core.duckdb_manager import get_duckdb
from app.core.quality_checker import QualityChecker
from app.core.ai_quality_checker import AIQualityChecker, AI_REPAIR_STRATEGIES
from app.core.database import get_db, async_session_factory
from app.core.security import get_current_user
from app.models.quality import QualityIssue, CleanRule, ChangeLog, QualityRowChange
from app.models.ai_action_log import AiActionLog
from app.models.dataset import Dataset
from app.api.datasets import _assert_dataset_access

router = APIRouter(prefix="/quality", tags=["Quality"])

# AI补充检测结果缓存：dataset_id -> {status: pending|running|done|failed, issues, ...}
# 主质检接口秒回规则检测结果，AI补充检测在后台异步完成，前端轮询本缓存取结果
_AI_RESULT_CACHE: Dict[str, Dict] = {}


def _serialize_ai_issues(ai_result, state_map: Optional[Dict] = None) -> List[Dict]:
    """将 AI 检测结果序列化为与规则检测一致的扁平结构（证据链 + 修复策略，Task #724/#34）。

    state_map: ai_issue_id -> {confirmation, repair, status}。重跑质检时从 DB 继承，
    否则用户已确认 / 已修复的结论会被新一轮 AI 结果静默重置（#35 根因之一）。
    """
    state_map = state_map or {}
    out = []
    for iss in ai_result.issues:
        st = state_map.get(iss.ai_issue_id) or {}
        out.append({
            "type": iss.type,
            "severity": iss.severity,
            "column": iss.column,
            "row_count": iss.row_count,
            "message": iss.message,
            "detail": iss.detail,
            "sample_values": iss.sample_values[:5],
            "rule": iss.rule,
            "source": "ai",
            "repair_options": QualityChecker.build_repair_options(iss.type, iss.column),
            # ↓ 证据链
            "ai_issue_id": iss.ai_issue_id,
            "plain_conclusion": iss.plain_conclusion,
            "basis": iss.basis,
            "involved_columns": iss.involved_columns,
            "check_suggestion": iss.check_suggestion,
            "evidence_filter": iss.evidence_filter,
            "row_numbers": iss.row_numbers,
            "evidence_available": True,
            # ↓ #34：AI 签发的修复策略 + #35：继承人工核对状态
            "repair_plan": iss.repair_plan or {},
            "repair": st.get("repair") or {},
            "confirmation": st.get("confirmation") or {"decision": "pending"},
            "status": st.get("status") or "todo",
        })
    return out


def _evidence_payload(issue: Dict) -> Dict:
    """把 AI 证据（DB 存于 fix_rule / 内存缓存是扁平字段）归一成同一结构。"""
    fr = issue.get("fix_rule")
    if not isinstance(fr, dict):
        fr = {}

    def pick(key, default):
        v = fr.get(key)
        if v not in (None, "", [], {}):
            return v
        alt = issue.get(key)
        return alt if alt not in (None, "", [], {}) else default

    return {
        "column": issue.get("column") or issue.get("field_name") or "",
        "ai_issue_id": pick("ai_issue_id", ""),
        "plain_conclusion": pick("plain_conclusion", ""),
        "basis": pick("basis", ""),
        "involved_columns": pick("involved_columns", []) or [],
        "check_suggestion": pick("check_suggestion", ""),
        "evidence_filter": pick("evidence_filter", []) or [],
        "row_numbers": pick("row_numbers", []) or [],
        "detail": pick("detail", ""),
        "sample_values": pick("sample_values", []) or [],
        "ai_sample_rows": fr.get("ai_sample_rows") or [],
        "sample_columns": fr.get("sample_columns") or [],
        "confirmation": pick("confirmation", {"decision": "pending"}),
        # #34：AI 修复策略 / 已执行的修复记录，DB 与缓存同构
        "repair_plan": pick("repair_plan", {}) or {},
        "repair": pick("repair", {}) or {},
        "status": issue.get("status") or "todo",
    }


def _build_evidence_where(evidence_filter, real_cols) -> tuple:
    """把 AI 给的定位条件编译成参数化 WHERE 子句。

    列名必须在真实表结构里、op 必须白名单、值全部走 ? 参数化；
    get_ai_evidence 与 ai-repair 共用同一份实现，杜绝两处防护口径漂移。
    """
    clauses, params = [], []
    for f in (evidence_filter or [])[:4]:
        if not isinstance(f, dict):
            continue
        col, op, val = str(f.get("column", "")), str(f.get("op", "eq")), f.get("value")
        if col not in real_cols:
            continue
        qc = '"%s"' % col.replace('"', '""')
        if op == "is_null":
            clauses.append(qc + " IS NULL")
        elif op == "in":
            vals = [v for v in (val if isinstance(val, list) else [val]) if v is not None][:8]
            if not vals:
                continue
            clauses.append("%s IN (%s)" % (qc, ",".join("?" for _ in vals)))
            params.extend(vals)
        elif op in ("gt", "lt"):
            try:
                params.append(float(val))
            except (TypeError, ValueError):
                continue
            clauses.append("TRY_CAST(%s AS DOUBLE) %s ?" % (qc, ">" if op == "gt" else "<"))
        elif op in ("eq", "neq"):
            if val is None:
                continue
            params.append(val)
            clauses.append("%s %s ?" % (qc, "=" if op == "eq" else "<>"))
    return clauses, params


async def _run_ai_check_in_background(
    dataset_id: str, table_name: str, columns: List[Dict], rule_issues: List[Dict]
) -> None:
    """
    后台执行AI补充检测，结果写入缓存供前端轮询。
    即使LLM慢或不可用，也只影响AI补充结果，不阻塞主质检返回。
    """
    cache = _AI_RESULT_CACHE.setdefault(dataset_id, {})
    cache["status"] = "running"
    try:
        # 后台任务内重新获取DB连接与brain配置
        db = get_duckdb()
        brain_config = {
            "null_threshold": 0.05,
            "format_threshold": 0.05,
            "duplicate_threshold": 0.01
        }
        ai_checker = AIQualityChecker(db, table_name, columns, brain_config)
        ai_result = await ai_checker.analyze(existing_issues=rule_issues)

        summary = ai_result.summary or {}
        if summary.get("ai_failed") or not summary.get("llm_called"):
            # 2026-11-12（#695）：全链失败绝不再伪装成 done / 「发现 0 个潜在问题」。
            # 前端据此显示琥珀色「规则兜底」，而不是绿色「AI 已参与」。
            cache["status"] = "failed"
            cache["issues"] = []
            cache["summary"] = summary
            cache["error"] = summary.get("failure_reason") or "LLM 全链失败，AI 未参与本次质检"
            cache["finished_at"] = time.time()
            print(f"[AI质检][{dataset_id}] 后台补充检测失败（AI 未参与）: {cache['error']}")
            return

        # #35：重跑 AI 检测前先读出用户已经做过的人工核对 / 修复结论，
        # 否则「上一步已确认过的两个问题」会被新结果静默重置成 pending，
        # 进而在生成看板时又弹一次「AI 发现 2 个问题」。
        prev_state: Dict[str, Dict] = {}
        try:
            async with async_session_factory() as _hist_db:
                _hr = await _hist_db.execute(
                    select(QualityIssue).where(
                        QualityIssue.dataset_id == dataset_id, QualityIssue.type == "ai"
                    )
                )
                for _h in _hr.scalars().all():
                    _hfr = _h.fix_rule or {}
                    _k = _hfr.get("ai_issue_id")
                    if _k and _k not in prev_state:
                        prev_state[_k] = {
                            "confirmation": _hfr.get("confirmation") or {"decision": "pending"},
                            "repair": _hfr.get("repair") or {},
                            "status": _h.status,
                            # #35：缓存丢失/服务重启时按 DB 重建面板记录所需的最小证据
                            "column": _h.field_name or _hfr.get("column") or "",
                            "message": _h.message or "",
                            "severity": _h.severity or "warning",
                            "detail": _hfr.get("detail") or "",
                            "plain_conclusion": _hfr.get("plain_conclusion") or "",
                            "basis": _hfr.get("basis") or "",
                            "evidence_filter": _hfr.get("evidence_filter") or [],
                            "row_numbers": _hfr.get("row_numbers") or [],
                            "repair_plan": _hfr.get("repair_plan") or {},
                        }
        except Exception as _he:
            print(f"[AI质检][{dataset_id}] 读取历史核对状态失败（不阻断）: {_he}")

        # #35：本次 AI 没再报出的「已人工确认 / 已标记无需处理且未修复」问题要保留，
        # 不能因为重跑一次就从面板静默消失；它们带 confirmation，不计入 unreviewed_count。
        prev_issues = list(cache.get("prev_issues") or cache.get("issues") or [])
        fresh_issues = _serialize_ai_issues(ai_result, prev_state)
        # #35 兜底：AI 换措辞 / 微调定位条件导致 id 仍漂移时，按「列 + 条件」指纹
        # 把人工核对结论迁移过来，避免同一问题被当成新问题重复打扰用户。
        def _fp(x):
            conds = sorted(
                "%s:%s:%s" % (f.get("column"), f.get("op"), f.get("value"))
                for f in (x.get("evidence_filter") or []) if isinstance(f, dict)
            )
            return (x.get("column"), tuple(conds))

        old_by_fp = {}
        for o in prev_issues:
            fp = _fp(o)
            if fp[1] and fp not in old_by_fp:
                old_by_fp[fp] = o
        for x in fresh_issues:
            st = prev_state.get(x.get("ai_issue_id")) or {}
            if (st.get("confirmation") or {}).get("decision") in ("confirmed", "ignored"):
                continue
            o = old_by_fp.get(_fp(x))
            if not o:
                continue
            dec = (o.get("confirmation") or {}).get("decision")
            if dec in ("confirmed", "ignored"):
                x["confirmation"] = o.get("confirmation")
                x["status"] = (prev_state.get(o.get("ai_issue_id")) or {}).get("status") or "todo"
        fresh_ids = {x.get("ai_issue_id") for x in fresh_issues}
        carried = []
        for old in prev_issues:
            oid = old.get("ai_issue_id")
            if not oid or oid in fresh_ids:
                continue
            st = prev_state.get(oid) or {}
            decision = (st.get("confirmation") or old.get("confirmation") or {}).get("decision")
            # 未修复即保留；已确认/已忽略由 confirmation 排除在 unreviewed_count 外，
            # 未确认的历史问题如实保留并计入待核对，不再静默消失。
            if not st.get("repair") and not old.get("repair"):
                keep = dict(old)
                keep["confirmation"] = st.get("confirmation") or old.get("confirmation")
                keep["repair"] = st.get("repair") or {}
                keep["status"] = st.get("status") or "todo"
                keep["carried_over"] = True
                carried.append(keep)

        # #35 通用兜底：缓存被清空 / 服务重启后 prev_issues 为空，
        # 仍按 DB 里持久化的人工结论重建已确认且未修复的问题，
        # 保证「上一步确认过的问题」不会在生成看板时又以新问题身份重复弹 toast。
        carried_ids = {x.get("ai_issue_id") for x in carried}
        for oid, st in prev_state.items():
            if not oid or oid in fresh_ids or oid in carried_ids:
                continue
            if st.get("repair"):
                continue
            carried.append({
                "ai_issue_id": oid,
                "column": st.get("column") or "",
                "message": st.get("message") or "已核对的 AI 补充检测问题",
                "severity": st.get("severity") or "warning",
                "detail": st.get("detail") or "",
                "plain_conclusion": st.get("plain_conclusion") or "",
                "basis": st.get("basis") or "",
                "evidence_filter": st.get("evidence_filter") or [],
                "row_numbers": st.get("row_numbers") or [],
                "repair_plan": st.get("repair_plan") or {},
                "confirmation": st.get("confirmation"),
                "repair": {},
                "status": st.get("status") or "todo",
                "carried_over": True,
                "restored_from_db": True,
            })

        cache["status"] = "done"
        cache["issues"] = fresh_issues + carried
        cache["summary"] = summary
        # 证据链：AI 判断时真实看到的前 8 行样本，供「查看明细数据」核对依据
        cache["evidence_sample"] = ai_result.evidence_sample
        cache["sample_columns"] = ai_result.sample_columns
        cache["finished_at"] = time.time()
        print(f"[AI质检][{dataset_id}] 后台补充检测完成（{summary.get('model')}），发现 {len(ai_result.issues)} 个潜在问题")

        # AI补充结果同步持久化到DB：按稳定 ai_issue_id 做 upsert，
        # 已存在则只刷新证据、保留人工核对与修复结论（#35），不再重复插入同 id 行。
        async with async_session_factory() as sql_db:
            _er = await sql_db.execute(
                select(QualityIssue).where(
                    QualityIssue.dataset_id == dataset_id, QualityIssue.type == "ai"
                )
            )
            existing_by_id = {}
            for _row in _er.scalars().all():
                _k = (_row.fix_rule or {}).get("ai_issue_id")
                if _k and _k not in existing_by_id:
                    existing_by_id[_k] = _row
            for iss in ai_result.issues:
                st = prev_state.get(iss.ai_issue_id) or {}
                evidence = {
                    "source": "ai",
                    "ai_issue_id": iss.ai_issue_id,
                    "detail": iss.detail,
                    "sample_values": iss.sample_values[:5],
                    "plain_conclusion": iss.plain_conclusion,
                    "basis": iss.basis,
                    "involved_columns": iss.involved_columns,
                    "check_suggestion": iss.check_suggestion,
                    "evidence_filter": iss.evidence_filter,
                    "row_numbers": iss.row_numbers,
                    "ai_sample_rows": ai_result.evidence_sample,
                    "sample_columns": ai_result.sample_columns,
                    # #34：AI 签发的修复策略随证据一起落库，刷新后仍可查看/执行
                    "repair_plan": iss.repair_plan or {},
                    "confirmation": st.get("confirmation") or {"decision": "pending"},
                }
                if st.get("repair"):
                    evidence["repair"] = st["repair"]
                old = existing_by_id.get(iss.ai_issue_id)
                if old is not None:
                    old.fix_rule = evidence
                    old.message = iss.message
                    old.affect_rows = iss.row_count
                    old.severity = iss.severity
                    old.status = st.get("status") or "todo"
                else:
                    sql_db.add(QualityIssue(
                        dataset_id=dataset_id,
                        field_name=iss.column,
                        type=iss.type,
                        severity=iss.severity,
                        status="todo",
                        message=iss.message,
                        affect_rows=iss.row_count,
                        fix_rule=evidence,
                    ))
            await sql_db.commit()
    except Exception as e:
        _AI_RESULT_CACHE[dataset_id]["status"] = "failed"
        _AI_RESULT_CACHE[dataset_id]["error"] = str(e)
        # Task #706：失败时显式给空 issues + 诚实 summary，避免只消费 issues 的调用方
        # 误判成「AI 检测完成且 0 个问题」（11-12 连续失败事故的同型谎言）。
        _AI_RESULT_CACHE[dataset_id]["issues"] = []
        _AI_RESULT_CACHE[dataset_id]["summary"] = {
            "ai_failed": True, "llm_called": False,
            "ai_badge_eligible": False, "failure_reason": str(e)[:200],
        }
        _AI_RESULT_CACHE[dataset_id]["finished_at"] = time.time()
        print(f"[AI质检][{dataset_id}] 后台补充检测失败: {e}")


class QualityCheckRequest(BaseModel):
    dataset_id: str
    rules: Optional[List[str]] = None


class QualityFixRequest(BaseModel):
    dataset_id: str
    issue_type: str
    column: str
    fix_strategy: str


def get_current_table(dataset_id: str) -> str:
    """
    获取当前质检需要读取的表
    
    优先读取最上层（清洗层），不存在则逐层向上找
    完整顺序：cleaned → norm → raw
    """
    db = get_duckdb()
    cleaned = db.get_layer_table_name(dataset_id, 'cleaned')
    if db.table_exists(cleaned):
        return cleaned
    norm = db.get_layer_table_name(dataset_id, 'norm')
    if db.table_exists(norm):
        return norm
    return db.get_layer_table_name(dataset_id, 'raw')


def get_cleaned_table(dataset_id: str) -> str:
    """获取或创建清洗层"""
    db = get_duckdb()
    return db.create_cleaned_from_original(dataset_id)




def _capture_column_stats(db, cleaned_table: str, column: str) -> dict:
    """清洗前后捕获字段统计快照（空值数/去重数/极值/样本），用于 change_log 行级明细。"""
    col = f'"{column}"'
    try:
        null_c = db.conn.execute(
            f"SELECT COUNT(*) FROM \"{cleaned_table}\" "
            f"WHERE {col} IS NULL OR TRIM(CAST({col} AS VARCHAR)) = ''"
        ).fetchone()[0]
        distinct_c = db.conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM \"{cleaned_table}\"").fetchone()[0]
        samples = [str(v[0]) for v in db.conn.execute(
            f"SELECT DISTINCT {col} FROM \"{cleaned_table}\" WHERE {col} IS NOT NULL LIMIT 5"
        ).fetchall()]
        stat = {"null_count": null_c, "distinct_count": distinct_c, "samples": samples}
        try:
            mn, mx = db.conn.execute(
                f"SELECT MIN(TRY_CAST({col} AS DOUBLE)), MAX(TRY_CAST({col} AS DOUBLE)) "
                f"FROM \"{cleaned_table}\" WHERE TRY_CAST({col} AS DOUBLE) IS NOT NULL"
            ).fetchone()
            if mn is not None:
                stat["min"] = mn
                stat["max"] = mx
        except Exception:
            pass
        return stat
    except Exception as e:
        return {"error": str(e)}


def _src_row_expr(db, cleaned_table: str) -> str:
    """返回可取「原始文件行号」的表达式：清洗层物化了 _src_row 列则用它，否则 rowid+2 近似（含表头偏移）。"""
    try:
        cols = [r[0].lower() for r in db.conn.execute(f"DESCRIBE \"{cleaned_table}\"").fetchall()]
        if "_src_row" in cols:
            return "_src_row"
    except Exception:
        pass
    return "(rowid + 2)"


def _capture_row_map(db, cleaned_table: str, column: str) -> Dict[int, Optional[str]]:
    """捕获某列「原始文件行号 -> 清洗前/后单元格值」的整列映射，供修复前后 diff 出逐行变更。"""
    try:
        src_expr = _src_row_expr(db, cleaned_table)
        col = f'"{column}"'
        rows = db.conn.execute(
            f"SELECT {src_expr}, CAST({col} AS VARCHAR) FROM \"{cleaned_table}\""
        ).fetchall()
        return {int(r[0]): (None if r[1] is None else str(r[1])) for r in rows}
    except Exception:
        return {}


def _build_row_changes(
    before_map: Dict[int, Optional[str]],
    after_map: Dict[int, Optional[str]],
    dataset_id: str,
    issue_type: Optional[str],
    column: str,
    strategy: str,
) -> List["QualityRowChange"]:
    """night45：对比修复前后整列映射，产出逐行 QualityRowChange。
    - 行消失（keep_first/keep_last/drop 等）→ after='(整行已删除)'；
    - 值变化 → before/after；mark_* 不改数据 → 空列表。"""
    changes: List[QualityRowChange] = []
    for src, before in before_map.items():
        if src not in after_map:
            changes.append(QualityRowChange(
                dataset_id=dataset_id, stage="apply", issue_type=issue_type,
                field_name=column, strategy=strategy, src_row=src,
                before_value=before, after_value="(整行已删除)", status="done",
            ))
        elif after_map[src] != before:
            changes.append(QualityRowChange(
                dataset_id=dataset_id, stage="apply", issue_type=issue_type,
                field_name=column, strategy=strategy, src_row=src,
                before_value=before, after_value=after_map[src], status="done",
            ))
    return changes


@router.post("/check")
async def check_quality(
    request: QualityCheckRequest,
    sql_db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    current_user: Dict = Depends(get_current_user)
):
    """
    执行质检（规则检测秒回 + AI补充检测后台异步）
    
    规则检测是阻断主闸门（毫秒级），先返回；AI补充检测放到后台任务跑，
    完成后前端通过 /quality/check/ai/{dataset_id} 轮询获取。
    这样用户感知的质检结果从 ~53秒 降至接近秒回，且不牺牲AI功能。
    """
    dataset_id = request.dataset_id
    db = get_duckdb()
    
    # 优先读取清洗层，不存在则读取原始层
    table_name = get_current_table(dataset_id)
    
    try:
        tables = db.list_tables()
        if table_name not in tables:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "TABLE_NOT_FOUND", "message": "数据集表不存在"}
            )
        
        table_info = db.get_table_info(table_name)
        
        brain_config = {
            "null_threshold": 0.05,
            "format_threshold": 0.05,
            "duplicate_threshold": 0.01
        }
        
        # 1. 规则检测（主闸门，毫秒级）
        t0_check = time.perf_counter()
        checker = QualityChecker(db, brain_config)
        rule_result = checker.check_table(table_name, table_info["columns"])
        rule_issues = rule_result.get("issues", [])
        t_rule_detect = time.perf_counter()
        
        # 重置该数据集的AI缓存，并后台异步启动AI补充检测
        # #35：整体替换会抹掉上一轮 issues，使后台的 carried-over / 指纹继承失效；
        # 先把上一轮面板问题显式保留下来（缓存被清或重启时后台另有 DB 兜底）。
        _prev_ai_issues = list((_AI_RESULT_CACHE.get(dataset_id) or {}).get("issues") or [])
        _AI_RESULT_CACHE[dataset_id] = {"status": "running", "prev_issues": _prev_ai_issues}
        if background_tasks is None:
            # 防御：无后台任务上下文时同步兜底（极少触发）
            await _run_ai_check_in_background(dataset_id, table_name, table_info["columns"], rule_issues)
        else:
            background_tasks.add_task(
                _run_ai_check_in_background, dataset_id, table_name, table_info["columns"], rule_issues
            )
        
        all_issues = rule_issues
        
        blocking_count = sum(1 for i in all_issues if i.get("severity") == "blocking")
        warning_count = len(all_issues) - blocking_count
        
        by_type = {}
        for issue in all_issues:
            t = issue.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        
        result = {
            "dataset_id": dataset_id,
            "table_name": table_name,
            "total_rows": table_info["row_count"],
            "issues": all_issues,
            "summary": {
                "total_issues": len(all_issues),
                "blocking_count": blocking_count,
                "warning_count": warning_count,
                "by_type": by_type,
                "can_proceed": blocking_count == 0,
                "ai_analysis": {
                    "status": "running",  # AI补充检测后台进行中
                    "ai_issues_count": 0,
                    "ai_analyzed": False,
                    "llm_called": False,
                    "fallback_used": False
                }
            }
        }
        
        # 保存规则检测结果到数据库（AI结果由后台任务完成后追加）
        # A1：规则类问题覆盖式重建——先 delete 再插新行，一次 commit（消除只增不删）
        # #35 根因修复：AI 类问题不能一起删。它们带着用户的人工核对结论与修复记录，
        # 后台任务按稳定 ai_issue_id upsert 刷新证据并继承 confirmation/repair/status；
        # 无条件删会让「上一步已确认的问题」在生成看板时又以新问题身份重复弹 toast。
        # 用户显式「重置」端点仍做全量清除，语义不变。
        t_write = time.perf_counter()
        await sql_db.execute(
            delete(QualityIssue).where(
                QualityIssue.dataset_id == dataset_id,
                or_(QualityIssue.type != "ai", QualityIssue.type.is_(None)),
            )
        )
        for iss in all_issues:
            qa = QualityIssue(
                dataset_id=dataset_id,
                field_name=iss.get("column", ""),
                type=iss.get("type", ""),
                severity=iss.get("severity", "warning"),
                status="todo",
                message=iss.get("message", ""),
                affect_rows=iss.get("row_count", 0),
            )
            sql_db.add(qa)
        await sql_db.commit()
        t_done = time.perf_counter()
        # A3：分段耗时日志
        print(f"[质检][{dataset_id}] 规则检测 {(t_rule_detect - t0_check)*1000:.1f}ms | "
              f"写库 {(t_done - t_write)*1000:.1f}ms | 总 {(t_done - t0_check)*1000:.1f}ms | 问题数 {len(all_issues)}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CHECK_ERROR", "message": f"质检失败: {str(e)}"}
        )


@router.get("/check/ai/{dataset_id}")
async def get_ai_check_result(dataset_id: str,current_user: Dict = Depends(get_current_user)):
    """
    轮询AI补充检测结果
    
    - status=running/pending: 仍在后台检测中
    - status=done: AI检测完成，返回 issues
    - status=failed: AI检测异常，返回 error（规则结果不受影响）
    """
    from app.core.ai_budget import chain_budget
    cache = _AI_RESULT_CACHE.get(dataset_id, {"status": "pending", "issues": []})
    ai_issues = cache.get("issues", [])
    blocking_count = sum(1 for i in ai_issues if i.get("severity") == "blocking")
    # #35：只统计「尚未人工核对」的 AI 问题。已确认属实 / 已标记无需处理的
    # 不应在生成看板时再弹一次 toast；重跑质检会继承 confirmation，见 B6。
    unreviewed_count = sum(
        1 for i in ai_issues
        if (i.get("confirmation") or {}).get("decision") not in ("confirmed", "ignored")
    )
    return {
        "dataset_id": dataset_id,
        "status": cache.get("status", "pending"),
        "issues": ai_issues,
        "ai_issues_count": len(ai_issues),
        "unreviewed_count": unreviewed_count,
        "blocking_count": blocking_count,
        "warning_count": len(ai_issues) - blocking_count,
        "error": cache.get("error"),
        "summary": cache.get("summary") or {},
        # Task #728/#33：把链路预算下发给前端，轮询上限按契约动态计算（单一真相源）
        "chain_budget_s": chain_budget("quality"),
    }


@router.get("/{dataset_id}/issues")
async def get_quality_issues(
    dataset_id: str,
    sql_db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取质检问题列表（G3：需登录 + 数据集归属校验）"""
    await _assert_dataset_access(sql_db, dataset_id, current_user)
    result = await sql_db.execute(
        select(QualityIssue).where(
            QualityIssue.dataset_id == dataset_id,
            QualityIssue.status != "ignored"
        )
    )
    issues = result.scalars().all()
    # 历史数据集从 DB 读取：QualityIssue 模型无 repair_options 列，需按规则重算，
    # 否则前端「处理方案」下拉框会因 [] 显示 'No data'
    serialized = []
    for i in issues:
        d = i.to_dict()
        d["repair_options"] = QualityChecker.build_repair_options(
            d.get("type", ""), d.get("field_name") or ""
        )
        if d.get("type") == "ai":
            # Task #724：刷新/历史数据集同样能读到证据链，「查看明细数据」不会时有时无
            ev = _evidence_payload(d)
            d.update({
                "column": ev["column"],
                "source": "ai",
                "detail": ev["detail"],
                "sample_values": ev["sample_values"],
                "ai_issue_id": ev["ai_issue_id"],
                "plain_conclusion": ev["plain_conclusion"],
                "basis": ev["basis"],
                "involved_columns": ev["involved_columns"],
                "check_suggestion": ev["check_suggestion"],
                "evidence_available": True,
                "confirmation": ev["confirmation"],
                "repair_plan": ev["repair_plan"],
                "repair": ev["repair"],
            })
        serialized.append(d)
    return {
        "dataset_id": dataset_id,
        "issues": serialized,
        "total_count": len(serialized)
    }


class AIRepairRequest(BaseModel):
    """#34：按 AI 建议（或用户改选的策略）执行行级修复。

    AI 只签发 patch；真正的数据改动全部由本端点的白名单规则引擎完成，
    写清洗层（可回滚）+ change_log/row_changes 行级留痕 + ai_action_log。
    """
    issue_id: str
    strategy: str = ""        # 空 = 采用 AI 建议的 repair_plan.strategy
    target_value: str = ""    # replace_with_constant 时的人工指定值


_CHANGE_STRATEGY_ALIAS = {
    "replace_with_column_median": "ai_repair_median",
    "replace_with_column_mean": "ai_repair_mean",
    "winsorize_p1_p99": "ai_repair_winsorize",
    "set_null": "ai_repair_set_null",
    "replace_with_constant": "ai_repair_constant",
}


def _as_number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@router.post("/{dataset_id}/ai-repair")
async def repair_ai_issue(
    dataset_id: str,
    request: AIRepairRequest,
    sql_db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """确认属实后，定点修复 AI 定位到的真实数据行（不是整列盲改）。"""
    await _assert_dataset_access(sql_db, dataset_id, current_user)
    res = await sql_db.execute(
        select(QualityIssue).where(
            QualityIssue.dataset_id == dataset_id, QualityIssue.type == "ai"
        )
    )
    db_row = next(
        (i for i in res.scalars().all()
         if (i.fix_rule or {}).get("ai_issue_id") == request.issue_id), None
    )
    cache = _AI_RESULT_CACHE.get(dataset_id, {})
    cache_issue = next(
        (x for x in (cache.get("issues") or [])
         if x.get("ai_issue_id") == request.issue_id), None
    )
    if db_row is None and cache_issue is None:
        raise HTTPException(404, detail={
            "code": "AI_ISSUE_NOT_FOUND", "message": "未找到该 AI 问题，请重新执行质检"})

    ev = _evidence_payload(db_row.to_dict()) if db_row is not None else _evidence_payload(cache_issue or {})
    confirmation = ev.get("confirmation") or {}
    if confirmation.get("decision") != "confirmed":
        raise HTTPException(400, detail={
            "code": "NOT_CONFIRMED",
            "message": "请先在明细弹窗里确认「问题属实」，再执行修复"})
    if ev.get("repair") or (db_row is not None and db_row.status == "done"):
        raise HTTPException(400, detail={
            "code": "ALREADY_REPAIRED", "message": "这条问题已经修复过，可在清洗修改明细里查看前后对比"})

    plan = ev.get("repair_plan") or {}
    strategy = (request.strategy or plan.get("strategy") or "keep_as_is").strip()
    if strategy not in AI_REPAIR_STRATEGIES or strategy == "keep_as_is":
        raise HTTPException(400, detail={
            "code": "STRATEGY_NOT_EXECUTABLE",
            "message": "AI 建议保留原值（或策略不合法），不自动修改数据；如需处理请在下方改选其他策略"})

    db = get_duckdb()
    cleaned_table = get_cleaned_table(dataset_id)   # 写清洗层：原始层不动，可用「重置」回滚
    if cleaned_table not in db.list_tables():
        raise HTTPException(404, detail={
            "code": "TABLE_NOT_FOUND", "message": "数据表不存在，无法执行修复"})
    real_cols = [str(c["name"]) for c in db.get_table_info(cleaned_table)["columns"]]
    column = ev.get("column") or ""
    if column not in real_cols:
        raise HTTPException(400, detail={
            "code": "BAD_COLUMN", "message": "AI 给出的字段不在真实表结构里，拒绝执行"})
    clauses, params = _build_evidence_where(ev.get("evidence_filter"), real_cols)
    if not clauses:
        raise HTTPException(400, detail={
            "code": "NO_LOCATOR",
            "message": "AI 没给出可精确定位的数据行，拒绝自动改动；请查看明细后人工处理"})
    where_sql = " WHERE " + " AND ".join(clauses)
    qc = '"%s"' % column.replace('"', '""')

    def _hit_count(p):
        return db.conn.execute(
            'SELECT COUNT(*) FROM "%s"%s' % (cleaned_table, where_sql), p
        ).fetchone()[0]

    affected = _hit_count(params)
    if affected == 0:
        # AI 给的样本值常是字符串，而真实列可能是 DOUBLE；做一次数值兼容重试
        alt = [_as_number(v) if isinstance(v, str) and _as_number(v) is not None else v
               for v in params]
        if alt != params:
            alt_count = _hit_count(alt)
            if alt_count:
                params, affected = alt, alt_count
    if affected == 0:
        raise HTTPException(400, detail={
            "code": "NO_MATCHED_ROWS", "message": "按 AI 定位条件没有匹配到数据行，未改动任何数据"})
    if affected > 20:
        raise HTTPException(400, detail={
            "code": "TOO_MANY_ROWS",
            "message": "定位到 %d 行，超过单次安全上限 20 行，请缩小范围或人工处理" % affected})

    meta = AI_REPAIR_STRATEGIES[strategy]
    replacement = None
    hit_subquery = 'SELECT rowid FROM "%s"%s' % (cleaned_table, where_sql)
    if strategy in ("replace_with_column_median", "replace_with_column_mean"):
        agg = "MEDIAN" if strategy.endswith("median") else "AVG"
        _r = db.conn.execute(
            'SELECT %s(TRY_CAST(%s AS DOUBLE)) FROM "%s" '
            'WHERE rowid NOT IN (%s) AND TRY_CAST(%s AS DOUBLE) IS NOT NULL'
            % (agg, qc, cleaned_table, hit_subquery, qc), params
        ).fetchone()
        if not _r or _r[0] is None:
            raise HTTPException(400, detail={
                "code": "NOT_NUMERIC",
                "message": "该字段不是数值列，无法计算中位数/均值；请改选「置空」或「指定值」"})
        replacement = float(_r[0])
    elif strategy == "replace_with_constant":
        replacement = (request.target_value or str(plan.get("target_value") or "")).strip()[:100]
        if not replacement:
            raise HTTPException(400, detail={
                "code": "MISSING_VALUE", "message": "请填写用于替换的正确值"})

    before_stats = _capture_column_stats(db, cleaned_table, column)
    before_row_map = _capture_row_map(db, cleaned_table, column)
    try:
        if strategy == "winsorize_p1_p99":
            _r = db.conn.execute(
                'SELECT quantile_cont(TRY_CAST(%s AS DOUBLE), 0.01), '
                'quantile_cont(TRY_CAST(%s AS DOUBLE), 0.99) FROM "%s" '
                'WHERE TRY_CAST(%s AS DOUBLE) IS NOT NULL'
                % (qc, qc, cleaned_table, qc)
            ).fetchone()
            if not _r or _r[0] is None or _r[1] is None:
                raise HTTPException(400, detail={
                    "code": "NOT_NUMERIC", "message": "该字段不是数值列，无法计算分位数"})
            lo, hi = float(_r[0]), float(_r[1])
            replacement = {"p1": lo, "p99": hi}
            db.conn.execute(
                'UPDATE "%s" SET %s = CASE '
                'WHEN TRY_CAST(%s AS DOUBLE) < ? THEN ? '
                'WHEN TRY_CAST(%s AS DOUBLE) > ? THEN ? ELSE %s END%s'
                % (cleaned_table, qc, qc, qc, qc, where_sql),
                [lo, lo, hi, hi] + params,
            )
        else:
            db.conn.execute(
                'UPDATE "%s" SET %s = ?%s' % (cleaned_table, qc, where_sql),
                [replacement] + params,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail={
            "code": "AI_REPAIR_FAILED", "message": "修复执行失败，数据未落盘：%s" % str(e)[:160]})

    after_stats = _capture_column_stats(db, cleaned_table, column)
    after_row_map = _capture_row_map(db, cleaned_table, column)
    alias = _CHANGE_STRATEGY_ALIAS.get(strategy, "ai_repair")
    row_changes = _build_row_changes(
        before_row_map, after_row_map, dataset_id, "ai", column, alias)
    sql_db.add(ChangeLog(
        dataset_id=dataset_id, issue_type="ai", field_name=column, strategy=alias,
        before_value=before_stats, after_value=after_stats, affected_rows=affected,
    ))
    for rc in row_changes:
        sql_db.add(rc)
    sql_db.add(CleanRule(
        dataset_id=dataset_id, rule_type="transform", target_field=column,
        params={"source": "ai_governor", "ai_issue_id": request.issue_id,
                "strategy": strategy, "affected_rows": affected},
    ))
    # 护栏四件套之一：AI 动作留痕（与对话链路同一张 ai_action_log）
    sql_db.add(AiActionLog(
        session_id=None, dashboard_id=None,
        user_id=str(current_user.get("user_id") or ""), run_id=None,
        intent="ai_quality_repair", action_type=strategy[:32],
        params_summary={"dataset_id": dataset_id, "issue_id": request.issue_id,
                        "column": column, "strategy": strategy,
                        "affected_rows": affected, "lineage_source": "ai_governor"},
        result_status="success", error_msg=None, llm_layer="ai_governor", latency_ms=0,
    ))

    repair_record = {
        "strategy": strategy, "label": meta["label"],
        "replacement": replacement, "affected_rows": affected,
        "by": str(current_user.get("user_id") or ""), "at": time.time(),
        "lineage_source": "ai_governor",
    }
    if db_row is not None:
        fr = dict(db_row.fix_rule or {})
        fr["repair"] = repair_record
        db_row.fix_rule = fr
        db_row.status = "done"
    if cache_issue is not None:
        cache_issue["repair"] = repair_record
        cache_issue["status"] = "done"
    await sql_db.commit()

    return {
        "dataset_id": dataset_id, "issue_id": request.issue_id,
        "status": "repaired", "strategy": strategy, "strategy_label": meta["label"],
        "column": column, "affected_rows": affected, "replacement": replacement,
        "changed_rows": len(row_changes), "before": before_stats, "after": after_stats,
        "repair": repair_record,
        "lineage_source": "ai_governor",
        "rollback_hint": "修复写在清洗层，原始层未动；可在质检页点「重置」撤销并回滚",
    }


class AIConfirmRequest(BaseModel):
    issue_id: str
    decision: str          # confirmed（问题属实）/ ignored（无需处理）/ pending（撤销结论）
    note: str = ""


@router.get("/{dataset_id}/ai-evidence/{issue_id}")
async def get_ai_evidence(
    dataset_id: str,
    issue_id: str,
    sql_db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """AI 补充检测问题下钻：AI 看到什么 + 真实数据长什么样 + 人该怎么核对。

    Task #724：证据全部来自真实 DuckDB 查询，绝不把「AI 说的」当成数据；
    AI 未给出 / 给出不可用的定位条件时，如实降级为表内前 20 行并标注原因。
    """
    await _assert_dataset_access(sql_db, dataset_id, current_user)
    res = await sql_db.execute(
        select(QualityIssue).where(
            QualityIssue.dataset_id == dataset_id, QualityIssue.type == "ai"
        )
    )
    db_row = next(
        (i for i in res.scalars().all() if (i.fix_rule or {}).get("ai_issue_id") == issue_id), None
    )
    if db_row is None:
        # 后端刚重启、AI 结果只存在于内存缓存（DB 提交稍晚于缓存写入）：按 id 兜底
        cache = _AI_RESULT_CACHE.get(dataset_id, {})
        c = next((x for x in (cache.get("issues") or [])
                  if x.get("ai_issue_id") == issue_id), None)
        if c is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "AI_ISSUE_NOT_FOUND", "message": "未找到该 AI 问题，请重新执行质检"},
            )
        ev = _evidence_payload(c)
        ev["ai_sample_rows"] = cache.get("evidence_sample") or []
        ev["sample_columns"] = cache.get("sample_columns") or []
    else:
        ev = _evidence_payload(db_row.to_dict())

    db = get_duckdb()
    table_name = get_current_table(dataset_id)
    if table_name not in db.list_tables():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TABLE_NOT_FOUND", "message": "数据集表不存在，无法查看明细数据"},
        )
    real_cols = [str(c["name"]) for c in db.get_table_info(table_name)["columns"]]
    involved = [c for c in (ev.get("involved_columns") or []) if c in real_cols]
    show_cols = involved[:8] or real_cols[:6]
    if ev.get("column") in real_cols and ev["column"] not in show_cols:
        show_cols.append(ev["column"])
    safe_cols = ", ".join('"%s"' % c.replace('"', '""') for c in show_cols)

    # #34：定位条件编译抽到共享函数，明细下钻与修复执行用同一套白名单/参数化防护
    clauses, params = _build_evidence_where(ev.get("evidence_filter"), real_cols)

    rns = [int(x) for x in (ev.get("row_numbers") or [])
           if isinstance(x, int) and 1 <= x <= 8][:8]
    locator = "head_sample"
    sql_note = "AI 未给出可用的行定位条件，展示表内前 20 行（涉及字段）供人工核对"
    where_sql = ""
    if clauses:
        where_sql = " WHERE " + " AND ".join(clauses)
        locator = "filter"
        sql_note = "按 AI 给出的定位条件筛出真实行：" + " 且 ".join(clauses)
    elif rns:
        locator = "ai_sample"
        sql_note = "AI 标注样本中第 %s 行可疑，已在下方「AI 判断依据样本」中高亮" % "、".join(map(str, rns))

    rows = []
    try:
        sql = "SELECT %s FROM %s%s LIMIT 20" % (safe_cols, table_name, where_sql)
        cur = db.conn.execute(sql, params) if params else db.conn.execute(sql)
        rows = [{c: (None if v is None else str(v)) for c, v in zip(show_cols, r)}
                for r in cur.fetchall()]
    except Exception as e:
        # AI 给的值类型不可靠 → 诚实降级，绝不伪装成"精确命中"
        locator = "head_sample"
        sql_note = "AI 定位条件无法执行（%s），已降级为表内前 20 行供人工核对" % str(e)[:80]
        try:
            cur = db.conn.execute("SELECT %s FROM %s LIMIT 20" % (safe_cols, table_name))
            rows = [{c: (None if v is None else str(v)) for c, v in zip(show_cols, r)}
                    for r in cur.fetchall()]
        except Exception as e2:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "EVIDENCE_QUERY_ERROR", "message": str(e2)[:200]},
            )
    for i, r in enumerate(rows, 1):
        r["_row_no"] = i

    seen = []
    for i, raw in enumerate((ev.get("ai_sample_rows") or [])[:8], 1):
        item = {k: (None if v is None else str(v)) for k, v in raw.items()}
        item["_row_no"] = i
        seen.append(item)

    return {
        "dataset_id": dataset_id,
        "issue_id": issue_id,
        "column": ev.get("column", ""),
        "plain_conclusion": ev.get("plain_conclusion") or "",
        "basis": ev.get("basis") or "",
        "involved_columns": involved,
        "check_suggestion": ev.get("check_suggestion") or "",
        "columns": show_cols,
        "rows": rows,
        "total_matched": len(rows),
        "locator": locator,
        "sql_note": sql_note,
        "ai_seen_rows": seen,
        "sample_columns": ev.get("sample_columns") or [],
        "highlight_rows": rns,
        "confirmation": ev.get("confirmation") or {"decision": "pending"},
        "repair_plan": ev.get("repair_plan") or {},
        "repair": ev.get("repair") or {},
        "repair_strategies": AI_REPAIR_STRATEGIES,
        "can_auto_repair": bool(clauses) and not ev.get("repair")
            and (ev.get("repair_plan") or {}).get("strategy") != "keep_as_is",
        "source": "duckdb",
    }


@router.post("/{dataset_id}/ai-confirm")
async def confirm_ai_issue(
    dataset_id: str,
    request: AIConfirmRequest,
    sql_db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """人工核对 AI 补充检测结论：确认属实 / 标记无需处理 / 撤销结论，落库留痕。"""
    if request.decision not in ("confirmed", "ignored", "pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BAD_DECISION", "message": "decision 只能是 confirmed / ignored / pending"},
        )
    await _assert_dataset_access(sql_db, dataset_id, current_user)
    res = await sql_db.execute(
        select(QualityIssue).where(
            QualityIssue.dataset_id == dataset_id, QualityIssue.type == "ai"
        )
    )
    target = next(
        (i for i in res.scalars().all() if (i.fix_rule or {}).get("ai_issue_id") == request.issue_id), None
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AI_ISSUE_NOT_FOUND", "message": "未找到该 AI 问题，请重新执行质检"},
        )
    fr = dict(target.fix_rule or {})
    fr["confirmation"] = {
        "decision": request.decision,
        "note": (request.note or "")[:200],
        "by": current_user.get("user_id"),
        "at": time.time(),
    }
    target.fix_rule = fr
    # 不用 "ignored"：/issues 会把它过滤掉，用户就再也查不到这条证据链了
    # 已执行修复的问题保持 done，撤销结论不能把「已修复」打回「待修复」
    _next_status = {"confirmed": "ai_confirmed", "ignored": "ai_dismissed", "pending": "todo"}[request.decision]
    target.status = "done" if target.status == "done" else _next_status
    await sql_db.commit()
    for c in (_AI_RESULT_CACHE.get(dataset_id, {}).get("issues") or []):
        if c.get("ai_issue_id") == request.issue_id:
            c["confirmation"] = fr["confirmation"]
    return {
        "dataset_id": dataset_id,
        "issue_id": request.issue_id,
        "decision": request.decision,
        "status": target.status,
        "confirmation": fr["confirmation"],
    }


@router.post("/fix")
async def fix_quality_issue(request: QualityFixRequest, sql_db: AsyncSession = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    """
    修复质量问题 — 写入清洗层
    
    流程：
    1. 创建清洗层表（如果不存在）
    2. 修复策略写入清洗层
    3. 标记质检记录为已修复
    """
    dataset_id = request.dataset_id
    cleaned_table = get_cleaned_table(dataset_id)
    db = get_duckdb()
    column = request.column.split(',')[0].strip()  # 多字段取第一个
    
    try:
        # 根据修复策略执行实际数据修改（写入清洗层）
        # B1：捕获清洗前字段统计快照（行级明细 before）
        before_stats = _capture_column_stats(db, cleaned_table, column)
        # night45：整列「行号 -> 值」映射，用于修复后逐行 diff 出 quality_row_changes
        before_row_map = _capture_row_map(db, cleaned_table, column)

        if request.fix_strategy == "keep_first":
            db.conn.execute(f"""
                DELETE FROM {cleaned_table} 
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM {cleaned_table} 
                    GROUP BY "{column}"
                )
            """)
            
        elif request.fix_strategy == "keep_last":
            db.conn.execute(f"""
                DELETE FROM {cleaned_table} 
                WHERE rowid NOT IN (
                    SELECT MAX(rowid) FROM {cleaned_table} 
                    GROUP BY "{column}"
                )
            """)
            
        elif request.fix_strategy in ("fill_mean", "fill_median"):
            agg = "AVG" if request.fix_strategy == "fill_mean" else "MEDIAN"
            # 用 TRY_CAST 而非 CAST：文本列无法转数值时得到 NULL 而非硬报错（DuckDB 对
            # 'C001'→DOUBLE 会直接抛 Conversion Error）。聚合结果为 NULL 说明该列非数值，
            # 自动退化为众数填充(fill_mode)，避免「文本列空值被推荐数值填充策略」导致该项修复失败。
            r = db.conn.execute(f"""
                SELECT {agg}(TRY_CAST("{column}" AS DOUBLE))
                FROM {cleaned_table}
                WHERE TRY_CAST("{column}" AS DOUBLE) IS NOT NULL
            """).fetchone()
            if r and r[0] is not None:
                db.conn.execute(f"""
                    UPDATE {cleaned_table}
                    SET "{column}" = {r[0]}
                    WHERE "{column}" IS NULL
                       OR TRY_CAST("{column}" AS VARCHAR) = ''
                       OR TRIM(TRY_CAST("{column}" AS VARCHAR)) = ''
                """)
            else:
                # 退化路径：该列非数值（如客户编号/日期文本），改用众数填充，确保空值被真正修复
                rm = db.conn.execute(f"""
                    SELECT "{column}" FROM {cleaned_table}
                    WHERE "{column}" IS NOT NULL AND TRIM(CAST("{column}" AS VARCHAR)) != ''
                    GROUP BY "{column}"
                    ORDER BY COUNT(*) DESC
                    LIMIT 1
                """).fetchone()
                if rm and rm[0] is not None:
                    db.conn.execute(f"""
                        UPDATE {cleaned_table}
                        SET "{column}" = ?
                        WHERE "{column}" IS NULL
                           OR TRY_CAST("{column}" AS VARCHAR) = ''
                           OR TRIM(TRY_CAST("{column}" AS VARCHAR)) = ''
                    """, [rm[0]])
                
        elif request.fix_strategy == "fill_mode":
            r = db.conn.execute(f"""
                SELECT "{column}" FROM {cleaned_table}
                WHERE "{column}" IS NOT NULL
                GROUP BY "{column}"
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """).fetchone()
            if r:
                v = r[0]
                db.conn.execute(f"""
                    UPDATE {cleaned_table} 
                    SET "{column}" = '{v}' 
                    WHERE "{column}" IS NULL
                       OR CAST("{column}" AS VARCHAR) = ''
                       OR TRIM(CAST("{column}" AS VARCHAR)) = ''
                """)
                
        elif request.fix_strategy == "fill_constant":
            db.conn.execute(f"""
                UPDATE {cleaned_table} 
                SET "{column}" = '0' 
                WHERE "{column}" IS NULL
                   OR CAST("{column}" AS VARCHAR) = ''
                   OR TRIM(CAST("{column}" AS VARCHAR)) = ''
            """)
            
        elif request.fix_strategy == "convert_standard":
            db.conn.execute(f"""
                UPDATE {cleaned_table} 
                SET "{column}" = CASE
                    WHEN TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y/%m/%d') IS NOT NULL
                        THEN STRFTIME(TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y/%m/%d'), '%Y-%m-%d')
                    WHEN TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y%m%d') IS NOT NULL
                        THEN STRFTIME(TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y%m%d'), '%Y-%m-%d')
                    WHEN TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y年%m月%d日') IS NOT NULL
                        THEN STRFTIME(TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y年%m月%d日'), '%Y-%m-%d')
                    ELSE "{column}"
                END
                WHERE TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y/%m/%d') IS NOT NULL
                   OR TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y%m%d') IS NOT NULL
                   OR TRY_STRPTIME(CAST("{column}" AS VARCHAR), '%Y年%m月%d日') IS NOT NULL
            """)

        elif request.fix_strategy == "coerce_numeric":
            # 文本型数字 → 真实数值列（写清洗层，不动原始层）
            # 三步：①清洗显示值(货币/千分位/空白) ②不可转残留(如'N/A')置NULL ③真正把列类型改为DOUBLE
            # 关键：仅改值是"伪转数"，列仍是VARCHAR，下游SUM/报表依然无法聚合；必须ALTER改列类型。
            # DuckDB(RE2) 不支持 \u00a0，须用 \x{00a0}
            col_v = f'"{column}"'
            pattern = r'[￥¥$\s\x{00a0},，]'
            # ① 清洗可解析的文本数字
            db.conn.execute(f"""
                UPDATE {cleaned_table}
                SET {col_v} = REGEXP_REPLACE(TRIM(CAST({col_v} AS VARCHAR)), '{pattern}', '', 'g')
                WHERE {col_v} IS NOT NULL AND TRIM(CAST({col_v} AS VARCHAR)) != ''
            """)
            # ② 非数值残留（如 'N/A'、'未知'）置 NULL，保证整列可转数值
            db.conn.execute(f"""
                UPDATE {cleaned_table}
                SET {col_v} = NULL
                WHERE {col_v} IS NOT NULL
                  AND TRY_CAST(CAST({col_v} AS VARCHAR) AS DOUBLE) IS NULL
            """)
            # ③ 真正改列类型，让下游能识别为数值并聚合
            db.conn.execute(f"""
                ALTER TABLE {cleaned_table} ALTER {col_v} SET DATA TYPE DOUBLE
            """)
            
        elif request.fix_strategy == "swap_values":
            cols = request.column.split(',')
            if len(cols) >= 2:
                c1, c2 = cols[0].strip(), cols[1].strip()
                db.conn.execute(f"""
                    UPDATE {cleaned_table} 
                    SET "{c1}" = "{c2}", "{c2}" = "{c1}"
                    WHERE CAST("{c1}" AS DATE) > CAST("{c2}" AS DATE)
                """)
                
        elif request.fix_strategy == "fill_boundary":
            r = db.conn.execute(f"""
                SELECT MEDIAN(CAST("{column}" AS DOUBLE)) 
                FROM {cleaned_table} 
                WHERE "{column}" IS NOT NULL
            """).fetchone()
            if r and r[0] is not None:
                db.conn.execute(f"""
                    UPDATE {cleaned_table} 
                    SET "{column}" = {r[0]} 
                    WHERE CAST("{column}" AS DOUBLE) < 0 OR CAST("{column}" AS DOUBLE) > 100
                """)
                
        elif request.fix_strategy == "map_closest":
            db.conn.execute(f"""
                UPDATE {cleaned_table} 
                SET "{column}" = '其他' 
                WHERE "{column}" = '其它'
            """)
            
        elif request.fix_strategy == "winsorize":
            # 缩尾处理（2026-09-17 对齐 B：截断到 P1/P99）。此前该策略未实现、点了等于没修。
            r = db.conn.execute(f"""
                SELECT quantile_cont(CAST("{column}" AS DOUBLE), 0.01),
                       quantile_cont(CAST("{column}" AS DOUBLE), 0.99)
                FROM {cleaned_table}
                WHERE "{column}" IS NOT NULL
            """).fetchone()
            if r and r[0] is not None and r[1] is not None and r[1] > r[0]:
                lo, hi = r[0], r[1]
                db.conn.execute(f"""
                    UPDATE {cleaned_table}
                    SET "{column}" = CASE
                        WHEN TRY_CAST("{column}" AS DOUBLE) < {lo} THEN {lo}
                        WHEN TRY_CAST("{column}" AS DOUBLE) > {hi} THEN {hi}
                        ELSE "{column}"
                    END
                    WHERE TRY_CAST("{column}" AS DOUBLE) IS NOT NULL
                """)

        elif request.fix_strategy == "set_today":
            # 未来日期修正为今天。此前该策略未实现、点了等于没修。
            db.conn.execute(f"""
                UPDATE {cleaned_table}
                SET "{column}" = CAST(CURRENT_DATE AS VARCHAR)
                WHERE TRY_CAST("{column}" AS DATE) > CURRENT_DATE
            """)

        elif request.fix_strategy in ("mark_anomaly", "mark_duplicate", "ignore"):
            pass  # 不做实际修改，仅标记状态（ignore=用户选择不处理，保留异常原样）

        # B1：捕获清洗后字段统计快照（行级明细 after）；mark_*/ignore 不实际改数据，不记 change_log
        after_stats = _capture_column_stats(db, cleaned_table, column)
        if request.fix_strategy not in ("mark_anomaly", "mark_duplicate", "ignore"):
            # 取该质检问题的影响行数（权威"影响行数"来源）
            _iss_res = await sql_db.execute(
                select(QualityIssue).where(
                    QualityIssue.dataset_id == dataset_id,
                    QualityIssue.type == request.issue_type,
                    QualityIssue.field_name == request.column,
                    QualityIssue.status == "todo",
                )
            )
            _iss = _iss_res.scalars().first()
            _affected = _iss.affect_rows if _iss else None
            sql_db.add(ChangeLog(
                dataset_id=dataset_id,
                issue_type=request.issue_type,
                field_name=request.column,
                strategy=request.fix_strategy,
                before_value=before_stats,
                after_value=after_stats,
                affected_rows=_affected,
            ))
            
        elif request.fix_strategy == "drop":
            db.conn.execute(f"""
                DELETE FROM {cleaned_table} 
                WHERE "{column}" IS NULL
                   OR CAST("{column}" AS VARCHAR) = ''
                   OR TRIM(CAST("{column}" AS VARCHAR)) = ''
            """)
        
        # night45：修复后整列映射，diff 出逐行变更并写入 quality_row_changes（附录 B 行级明细）
        # mark_* 不实际改数据 → diff 为空，自然跳过。
        after_row_map = _capture_row_map(db, cleaned_table, column)
        for _rc in _build_row_changes(before_row_map, after_row_map, dataset_id, request.issue_type, request.column, request.fix_strategy):
            sql_db.add(_rc)

        # 记录清洗规则（血缘层④白盒展示：清洗动作 → 血缘页可见）
        _RULE_TYPE_MAP = {
            "keep_first": "remove_duplicate", "keep_last": "remove_duplicate",
            "fill_mean": "fill_null", "fill_median": "fill_null", "fill_mode": "fill_null",
            "fill_constant": "fill_null", "fill_boundary": "transform", "winsorize": "transform",
            "coerce_numeric": "format", "convert_standard": "format", "map_closest": "format",
            "set_today": "format", "swap_values": "transform", "drop": "filter",
        }
        rule_type = _RULE_TYPE_MAP.get(request.fix_strategy)
        if rule_type and request.fix_strategy not in ("mark_anomaly", "mark_duplicate", "ignore"):
            sql_db.add(CleanRule(
                dataset_id=dataset_id,
                rule_type=rule_type,
                target_field=request.column.split(',')[0].strip() or None,
                params={"strategy": request.fix_strategy, "issue_type": request.issue_type},
            ))

        # 标记质检记录为已修复
        stmt = (
            update(QualityIssue)
            .where(
                QualityIssue.dataset_id == dataset_id,
                QualityIssue.type == request.issue_type,
                QualityIssue.field_name == request.column
            )
            .values(status="done")
        )
        result = await sql_db.execute(stmt)
        await sql_db.flush()
        
        return {
            "message": "修复成功，已写入清洗层",
            "fix_strategy": request.fix_strategy,
            "dataset_id": dataset_id,
            "cleaned_table": cleaned_table
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "FIX_ERROR", "message": f"修复失败: {str(e)}"}
        )


class QualityFixBatchItem(BaseModel):
    issue_type: str
    column: str
    fix_strategy: str


class QualityFixBatchRequest(BaseModel):
    dataset_id: str
    items: List[QualityFixBatchItem]


@router.post("/fix-batch")
async def fix_quality_issues_batch(request: QualityFixBatchRequest, sql_db: AsyncSession = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    """
    批量修复 — "一键采纳推荐方案"（2026-09-17 对齐 B 的推荐清洗计划交互）。
    逐项复用 /quality/fix 的单条逻辑；单项失败不中断批次，逐条回执。
    """
    results = []
    success = 0
    t_batch = time.perf_counter()
    for idx, item in enumerate(request.items):
        t_item = time.perf_counter()
        try:
            await fix_quality_issue(
                QualityFixRequest(
                    dataset_id=request.dataset_id,
                    issue_type=item.issue_type,
                    column=item.column,
                    fix_strategy=item.fix_strategy,
                ),
                sql_db,
            )
            # A2：单项结束即提交，缩短写事务窗口，消除与后台AI检测/并发请求的 SQLite 写锁竞争（database is locked）
            await sql_db.commit()
            success += 1
            dt = (time.perf_counter() - t_item) * 1000
            results.append({"index": idx, "column": item.column, "strategy": item.fix_strategy, "ok": True})
            print(f"[批量修复][{request.dataset_id}] 项#{idx} {item.column}/{item.fix_strategy} 成功 {dt:.1f}ms")
        except HTTPException as e:
            await sql_db.rollback()
            dt = (time.perf_counter() - t_item) * 1000
            results.append({
                "index": idx, "column": item.column, "strategy": item.fix_strategy, "ok": False,
                "error": (e.detail or {}).get("message") if isinstance(e.detail, dict) else str(e.detail),
            })
            print(f"[批量修复][{request.dataset_id}] 项#{idx} {item.column}/{item.fix_strategy} 失败 {dt:.1f}ms: {results[-1]['error']}")
        except Exception as e:
            await sql_db.rollback()
            dt = (time.perf_counter() - t_item) * 1000
            results.append({"index": idx, "column": item.column, "strategy": item.fix_strategy, "ok": False, "error": str(e)})
            print(f"[批量修复][{request.dataset_id}] 项#{idx} {item.column}/{item.fix_strategy} 异常 {dt:.1f}ms: {str(e)}")
    t_batch_done = (time.perf_counter() - t_batch) * 1000
    # A3：总耗时 + 逐项(ms)日志
    print(f"[批量修复][{request.dataset_id}] 总 {t_batch_done:.1f}ms | 成功 {success}/{len(request.items)} | "
          f"单项(ms)={[ 'OK' if r['ok'] else 'FAIL' for r in results ]}")
    return {
        "dataset_id": request.dataset_id,
        "total": len(request.items),
        "success": success,
        "failed": len(request.items) - success,
        "results": results,
        "message": f"批量修复完成：成功 {success} 项" + (f"，失败 {len(request.items) - success} 项" if success < len(request.items) else ""),
    }


@router.post("/{dataset_id}/reset")
async def reset_quality(
    dataset_id: str,
    sql_db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """
    重置质检 — 撤销清洗层写入，回滚到原始数据（ISS-064）。
    仅本人/超管可操作（_assert_dataset_access 校验归属，否则 404）。
    动作：
      1) 删除清洗层物理表（cleaned），使后续质检重新读取 raw/norm 原始数据；
      2) 所有 QualityIssue.status 置为 ignored，撤销已采纳的修复；
      3) 清除该数据集的 AI 补充检测缓存，下次质检重新走规则+AI。
    """
    # 归属校验：非本人/非超管/无 owner 一律 404，杜绝越权重置他人数据
    await _assert_dataset_access(sql_db, dataset_id, current_user)

    db = get_duckdb()
    cleaned = db.get_layer_table_name(dataset_id, "cleaned")
    dropped = False
    if db.table_exists(cleaned):
        db.conn.execute(f'DROP TABLE IF EXISTS "{cleaned}"')
        dropped = True

    # A1：覆盖式清空该 dataset 的质检问题与清洗规则（而非置 ignored 累积），一次 commit
    await sql_db.execute(delete(QualityIssue).where(QualityIssue.dataset_id == dataset_id))
    await sql_db.execute(delete(CleanRule).where(CleanRule.dataset_id == dataset_id))
    await sql_db.commit()

    # 清除 AI 补充检测缓存，使下次质检重新走规则+AI
    _AI_RESULT_CACHE.pop(dataset_id, None)

    return {
        "dataset_id": dataset_id,
        "dropped_cleaned": dropped,
        "message": "已重置质检并撤销清洗层（数据已回滚到原始状态）",
    }




@router.get("/{dataset_id}/change-log")
async def get_change_log(
    dataset_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sql_db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取清洗修复的行级变更明细（before/after 快照），需登录 + 数据集归属校验（ISS-051）。"""
    await _assert_dataset_access(sql_db, dataset_id, current_user)
    result = await sql_db.execute(
        select(ChangeLog)
        .where(ChangeLog.dataset_id == dataset_id)
        .order_by(ChangeLog.created_at.desc())
        .limit(limit).offset(offset)
    )
    rows = result.scalars().all()
    total_res = await sql_db.execute(
        select(func.count()).select_from(ChangeLog).where(ChangeLog.dataset_id == dataset_id)
    )
    total = total_res.scalar() or 0
    return {
        "dataset_id": dataset_id,
        "change_logs": [c.to_dict() for c in rows],
        "total_count": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/_internal/test-quality")
async def test_quality_check(current_user: Dict = Depends(get_current_user)):
    """内部接口：测试质检功能（验收用）"""
    try:
        db = get_duckdb()
        
        import pandas as pd
        import uuid
        
        df = pd.DataFrame({
            "借据编号": ["JJ001", "JJ002", "JJ001", "JJ004", None],
            "放款日期": ["2024-01-01", "2024/01/05", "20240101", "2024年01月10日", "invalid"],
            "到期日期": ["2025-01-01", "2024-12-01", "2025-02-01", "2024-01-05", "2025-03-01"],
            "贷款金额": [100000, 200000, 150000, 300000, 250000],
            "抵押率": [0.7, 1.2, 0.8, 0.75, 0],
            "担保类型": ["信用", "抵押", "质押", "其它", "信用"]
        })
        
        dataset_id = "test_quality_" + str(uuid.uuid4())[:8]
        table_name = db.create_dataset_table(dataset_id, df)
        table_info = db.get_table_info(table_name)
        
        brain_config = {
            "null_threshold": 0.01,
            "format_threshold": 0.01
        }
        checker = QualityChecker(db, brain_config)
        result = checker.check_table(table_name, table_info["columns"])
        
        return {
            "message": "测试质检完成",
            "dataset_id": dataset_id,
            "table_name": table_name,
            "test_data": df.to_dict(),
            **result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(e)}
        )


@router.get("/debug/clean-stats")
async def debug_clean_stats(
    dataset_id: str,
    column: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)):
    """
    只读查询清洗层实时统计 - 用于从外部(HTTP)验证去重/清洗是否真实写入 DuckDB。
    查询在 uvicorn 进程内复用全局 DuckDB 连接，不受单进程文件锁限制。
    返回原始层/清洗层行数、聚类列、去重后剩余重复行数与空值数。
    """
    db = get_duckdb()
    try:
        cleaned = db.get_layer_table_name(dataset_id, "cleaned")
        if not db.table_exists(cleaned):
            return {"exists": False, "dataset_id": dataset_id, "message": "清洗层尚未生成"}

        raw = db.get_layer_table_name(dataset_id, "raw")
        raw_rows = db.conn.execute(f'SELECT COUNT(*) FROM "{raw}"').fetchone()[0] if db.table_exists(raw) else None
        clean_rows = db.conn.execute(f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
        cols = [c["name"] for c in db.get_table_info(cleaned)["columns"]]

        # 探测聚类(去重)列：优先显式指定，其次含"借据"的列，最后常见编号类列
        col = column
        if not col:
            col = next((c for c in cols if "借据" in c), None)
        if not col:
            col = next((c for c in cols if c in ("编号", "序号", "借据编号", "客户编号", "合同号")), None)

        stats = {
            "exists": True,
            "dataset_id": dataset_id,
            "raw_table": raw,
            "cleaned_table": cleaned,
            "raw_rows": raw_rows,
            "cleaned_rows": clean_rows,
            "diff_rows": (raw_rows - clean_rows) if raw_rows is not None else None,
            "column_count": len(cols),
            "dedup_column": col,
        }
        if col:
            non_null = db.conn.execute(
                f'SELECT COUNT(*) FROM "{cleaned}" WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS VARCHAR)) != \'\''
            ).fetchone()[0]
            distinct = db.conn.execute(f'SELECT COUNT(DISTINCT "{col}") FROM "{cleaned}"').fetchone()[0]
            duplicate_remaining = non_null - distinct
            stats["dedup_column"] = col
            stats["non_null_rows"] = non_null
            stats["distinct_count"] = distinct
            stats["duplicate_remaining"] = max(duplicate_remaining, 0)
            stats["null_count"] = clean_rows - non_null
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"清洗层查询失败: {e}"}
        )


class InjectDupRequest(BaseModel):
    dataset_id: str
    column: Optional[str] = None
    count: int = 3


@router.post("/debug/inject-dup")
async def debug_inject_dup(req: InjectDupRequest, current_user: Dict = Depends(get_current_user)):
    """
    [仅调试] 在指定 dataset 的清洗层按聚类列临时复制几行制造重复，用于端到端演示/验证
    "造重复 → 对话质量修复 → 去重归零" 的完整闭环。影响仅在清洗层，不影响输出层看板。
    """
    db = get_duckdb()
    cleaned = db.get_layer_table_name(req.dataset_id, "cleaned")
    if not db.table_exists(cleaned):
        raise HTTPException(status_code=404, detail={"message": "清洗层不存在，请先上传/清洗"})
    cols = [c["name"] for c in db.get_table_info(cleaned)["columns"]]
    col = req.column
    if not col:
        col = next((c for c in cols if "借据" in c), None) or next(
            (c for c in cols if c in ("编号", "序号", "借据编号", "客户编号", "合同号")), None)
    if not col:
        raise HTTPException(status_code=400, detail={"message": "无法定位可去重列，请显式传入column"})
    n = max(1, min(int(req.count), 50))
    db.conn.execute(f'INSERT INTO "{cleaned}" SELECT * FROM (SELECT * FROM "{cleaned}" LIMIT {n})')
    rows = db.conn.execute(f'SELECT COUNT(*) FROM "{cleaned}"').fetchone()[0]
    dup = db.conn.execute(f'SELECT COUNT(*) - COUNT(DISTINCT "{col}") FROM "{cleaned}"').fetchone()[0]
    return {"inserted": n, "column": col, "cleaned_rows": rows,
            "duplicate_remaining": max(dup, 0), "message": f"已注入{n}条重复(列:{col})"}