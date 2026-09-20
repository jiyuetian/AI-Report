"""质检API - M1-08a/b 六类质检 + AI补充检测 + 清洗层写入"""
import time
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

from app.core.duckdb_manager import get_duckdb
from app.core.quality_checker import QualityChecker
from app.core.ai_quality_checker import AIQualityChecker
from app.core.database import get_db, async_session_factory
from app.models.quality import QualityIssue, CleanRule

router = APIRouter(prefix="/quality", tags=["Quality"])

# AI补充检测结果缓存：dataset_id -> {status: pending|running|done|failed, issues, ...}
# 主质检接口秒回规则检测结果，AI补充检测在后台异步完成，前端轮询本缓存取结果
_AI_RESULT_CACHE: Dict[str, Dict] = {}


def _serialize_ai_issues(ai_result) -> List[Dict]:
    """将AI检测结果对象序列化为与规则检测一致的扁平结构"""
    out = []
    for iss in ai_result.issues:
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
            "repair_options": iss.repair_options or []
        })
    return out


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

        cache["status"] = "done"
        cache["issues"] = _serialize_ai_issues(ai_result)
        cache["summary"] = ai_result.summary
        cache["finished_at"] = time.time()
        print(f"[AI质检][{dataset_id}] 后台补充检测完成，发现 {len(ai_result.issues)} 个潜在问题")

        # AI补充结果同步持久化到DB，保证历史与修复审计不丢
        async with async_session_factory() as sql_db:
            for iss in ai_result.issues:
                sql_db.add(QualityIssue(
                    dataset_id=dataset_id,
                    field_name=iss.column,
                    type=iss.type,
                    severity=iss.severity,
                    status="todo",
                    message=iss.message,
                    affect_rows=iss.row_count,
                ))
            await sql_db.commit()
    except Exception as e:
        _AI_RESULT_CACHE[dataset_id]["status"] = "failed"
        _AI_RESULT_CACHE[dataset_id]["error"] = str(e)
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


@router.post("/check")
async def check_quality(
    request: QualityCheckRequest,
    sql_db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None
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
        checker = QualityChecker(db, brain_config)
        rule_result = checker.check_table(table_name, table_info["columns"])
        rule_issues = rule_result.get("issues", [])
        
        # 重置该数据集的AI缓存，并后台异步启动AI补充检测
        _AI_RESULT_CACHE[dataset_id] = {"status": "running"}
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
        await sql_db.execute(
            update(QualityIssue)
            .where(QualityIssue.dataset_id == dataset_id)
            .values(status="ignored")
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
        
        await sql_db.flush()
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CHECK_ERROR", "message": f"质检失败: {str(e)}"}
        )


@router.get("/check/ai/{dataset_id}")
async def get_ai_check_result(dataset_id: str):
    """
    轮询AI补充检测结果
    
    - status=running/pending: 仍在后台检测中
    - status=done: AI检测完成，返回 issues
    - status=failed: AI检测异常，返回 error（规则结果不受影响）
    """
    cache = _AI_RESULT_CACHE.get(dataset_id, {"status": "pending", "issues": []})
    ai_issues = cache.get("issues", [])
    blocking_count = sum(1 for i in ai_issues if i.get("severity") == "blocking")
    return {
        "dataset_id": dataset_id,
        "status": cache.get("status", "pending"),
        "issues": ai_issues,
        "ai_issues_count": len(ai_issues),
        "blocking_count": blocking_count,
        "warning_count": len(ai_issues) - blocking_count,
        "error": cache.get("error"),
        "summary": cache.get("summary") or {},
    }


@router.get("/{dataset_id}/issues")
async def get_quality_issues(dataset_id: str, sql_db: AsyncSession = Depends(get_db)):
    """获取质检问题列表"""
    result = await sql_db.execute(
        select(QualityIssue).where(
            QualityIssue.dataset_id == dataset_id,
            QualityIssue.status != "ignored"
        )
    )
    issues = result.scalars().all()
    return {
        "dataset_id": dataset_id,
        "issues": [i.to_dict() for i in issues],
        "total_count": len(issues)
    }


@router.post("/fix")
async def fix_quality_issue(request: QualityFixRequest, sql_db: AsyncSession = Depends(get_db)):
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
            r = db.conn.execute(f"""
                SELECT {agg}(CAST("{column}" AS DOUBLE)) 
                FROM {cleaned_table} 
                WHERE "{column}" IS NOT NULL
            """).fetchone()
            if r and r[0] is not None:
                db.conn.execute(f"""
                    UPDATE {cleaned_table} 
                    SET "{column}" = {r[0]} 
                    WHERE "{column}" IS NULL
                       OR CAST("{column}" AS VARCHAR) = ''
                       OR TRIM(CAST("{column}" AS VARCHAR)) = ''
                """)
                
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

        elif request.fix_strategy in ("mark_anomaly", "mark_duplicate"):
            pass  # 不做实际修改，仅标记状态
            
        elif request.fix_strategy == "drop":
            db.conn.execute(f"""
                DELETE FROM {cleaned_table} 
                WHERE "{column}" IS NULL
                   OR CAST("{column}" AS VARCHAR) = ''
                   OR TRIM(CAST("{column}" AS VARCHAR)) = ''
            """)
        
        # 记录清洗规则（血缘层④白盒展示：清洗动作 → 血缘页可见）
        _RULE_TYPE_MAP = {
            "keep_first": "remove_duplicate", "keep_last": "remove_duplicate",
            "fill_mean": "fill_null", "fill_median": "fill_null", "fill_mode": "fill_null",
            "fill_constant": "fill_null", "fill_boundary": "transform", "winsorize": "transform",
            "coerce_numeric": "format", "convert_standard": "format", "map_closest": "format",
            "set_today": "format", "swap_values": "transform", "drop": "filter",
        }
        rule_type = _RULE_TYPE_MAP.get(request.fix_strategy)
        if rule_type and request.fix_strategy not in ("mark_anomaly", "mark_duplicate"):
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
async def fix_quality_issues_batch(request: QualityFixBatchRequest, sql_db: AsyncSession = Depends(get_db)):
    """
    批量修复 — "一键采纳推荐方案"（2026-09-17 对齐 B 的推荐清洗计划交互）。
    逐项复用 /quality/fix 的单条逻辑；单项失败不中断批次，逐条回执。
    """
    results = []
    success = 0
    for idx, item in enumerate(request.items):
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
            success += 1
            results.append({"index": idx, "column": item.column, "strategy": item.fix_strategy, "ok": True})
        except HTTPException as e:
            await sql_db.rollback()
            results.append({
                "index": idx, "column": item.column, "strategy": item.fix_strategy, "ok": False,
                "error": (e.detail or {}).get("message") if isinstance(e.detail, dict) else str(e.detail),
            })
        except Exception as e:
            await sql_db.rollback()
            results.append({"index": idx, "column": item.column, "strategy": item.fix_strategy, "ok": False, "error": str(e)})
    return {
        "dataset_id": request.dataset_id,
        "total": len(request.items),
        "success": success,
        "failed": len(request.items) - success,
        "results": results,
        "message": f"批量修复完成：成功 {success} 项" + (f"，失败 {len(request.items) - success} 项" if success < len(request.items) else ""),
    }


@router.post("/_internal/test-quality")
async def test_quality_check():
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
):
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
async def debug_inject_dup(req: InjectDupRequest):
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