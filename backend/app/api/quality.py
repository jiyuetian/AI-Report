"""质检API - M1-08a/b 六类质检 + AI补充检测 + 清洗层写入"""
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List

from app.core.duckdb_manager import get_duckdb
from app.core.quality_checker import QualityChecker
from app.core.ai_quality_checker import AIQualityChecker
from app.core.database import get_db
from app.models.quality import QualityIssue

router = APIRouter(prefix="/quality", tags=["Quality"])


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
async def check_quality(request: QualityCheckRequest, sql_db: AsyncSession = Depends(get_db)):
    """
    执行全量质检（规则检测 + AI补充检测）
    
    读取清洗层数据（如果清洗层存在），否则读取原始层数据
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
        
        # 1. 规则检测
        checker = QualityChecker(db, brain_config)
        rule_result = checker.check_table(table_name, table_info["columns"])
        rule_issues = rule_result.get("issues", [])
        
        # 2. AI补充检测
        ai_checker = AIQualityChecker(db, table_name, table_info["columns"], brain_config)
        ai_result = await ai_checker.analyze(existing_issues=rule_issues)
        
        ai_issues = []
        for iss in ai_result.issues:
            ai_issues.append({
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
        
        all_issues = rule_issues + ai_issues
        
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
                    "ai_issues_count": len(ai_issues),
                    "ai_analyzed": ai_result.summary.get("ai_analyzed", False),
                    "llm_called": ai_result.summary.get("llm_called", False),
                    "fallback_used": ai_result.summary.get("fallback_used", False)
                }
            }
        }
        
        # 保存质检结果到数据库
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
            
        elif request.fix_strategy in ("mark_anomaly", "mark_duplicate"):
            pass  # 不做实际修改，仅标记状态
            
        elif request.fix_strategy == "drop":
            db.conn.execute(f"""
                DELETE FROM {cleaned_table} 
                WHERE "{column}" IS NULL
                   OR CAST("{column}" AS VARCHAR) = ''
                   OR TRIM(CAST("{column}" AS VARCHAR)) = ''
            """)
        
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