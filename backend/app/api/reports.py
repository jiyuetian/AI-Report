"""
报告 API - M3-01/M3-02
生成7章节HTML报告 + 导出
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
import uuid
from datetime import datetime

from app.core.database import get_db
from app.models.dataset import Dataset
from app.models.dashboard import Dashboard
from app.models.quality import QualityIssue
from app.core.duckdb_manager import DuckDBManager, get_duckdb
from app.core.report_generator import ReportGenerator
from app.core.llm_gateway import llm_chat
from app.core.config import settings, _PROJECT_ROOT

router = APIRouter(prefix="/reports", tags=["Reports"])


class ReportRequest(BaseModel):
    dashboard_id: str = Field(..., description="看板ID")
    force_regenerate: bool = Field(False, description="强制重新生成")


class ReportResponse(BaseModel):
    success: bool
    report_id: str
    title: str
    llm_used: bool
    chart_count: int
    generated_at: str
    html_url: Optional[str] = None


@router.post("")
async def generate_report(
    request: ReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    生成7章节分析报告
    返回report_id，通过GET /reports/{report_id}/html获取HTML
    """
    # 查询看板
    result = await db.execute(select(Dashboard).where(Dashboard.id == request.dashboard_id))
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise HTTPException(status_code=404, detail="看板不存在")

    # 查询数据集
    primary_dataset_id = dashboard.primary_dataset_id or (
        dashboard.dataset_ids[0] if dashboard.dataset_ids else None
    )
    if not primary_dataset_id:
        raise HTTPException(status_code=400, detail="看板未关联数据集")

    ds_result = await db.execute(select(Dataset).where(Dataset.id == primary_dataset_id))
    dataset = ds_result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")

    # 构建dataset_info
    # schema_json["columns"] = [{"name":..,"type":..}]（DuckDB原生类型）
    schema = dataset.schema_json or {}
    raw_cols = schema.get("columns", [])
    profile = dataset.profile_json or {}
    _num_types = {"INTEGER", "BIGINT", "SMALLINT", "TINYINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "HUGEINT", "REAL"}
    _date_types = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"}
    field_profiles = []
    for c in raw_cols:
        nm = c.get("name", "")
        dt = (c.get("type") or "").upper()
        if dt in _num_types:
            ftype = "NUMBER"
        elif dt in _date_types:
            ftype = "DATE"
        else:
            ftype = "CATEGORY"
        field_profiles.append({"name": nm, "type": ftype, "cardinality": 0, "missing_rate": 0})

    # P1: 文档型数据集（docx/pdf/md/txt）无 DuckDB 表，走文本分支
    if not dataset.duckdb_table:
        extracted_text = profile.get("extracted_text") or ""
        dataset_info = {
            "source_type": "document",
            "table_name": None,
            "row_count": 0,
            "column_count": 0,
            "field_profiles": [],
            "theme": dashboard.name or "数据分析报告",
            "description": dashboard.description or "",
            "file_ext": schema.get("file_ext"),
            "char_count": len(extracted_text),
            "extracted_text": extracted_text,
        }
    else:
        # DuckDB 表名规则: ds_{dataset_id.replace('-', '_')}
        table_name = dataset.duckdb_table or f"ds_{primary_dataset_id.replace('-', '_')}"
        dataset_info = {
            "source_type": "table",
            "table_name": table_name,
            "row_count": dataset.row_count or 0,
            "column_count": len(field_profiles),
            "field_profiles": field_profiles,
            "theme": dashboard.name or "数据分析报告",
            "description": dashboard.description or "",
            "file_ext": schema.get("file_ext"),
        }

    # 构建dashboard_config
    config_raw = dashboard.config or {}
    dashboard_config = {
        "charts": config_raw.get("charts", []),
        "goals": config_raw.get("goals", []),
        "analysis_text": config_raw.get("analysis_text", ""),
    }

    # 查询质量异常
    q_result = await db.execute(
        select(QualityIssue).where(QualityIssue.dataset_id == primary_dataset_id).limit(20)
    )
    quality_issues = [
        {
            "issue_type": qi.issue_type,
            "column": qi.column,
            "severity": qi.severity,
            "message": qi.message,
        }
        for qi in q_result.scalars().all()
    ]

    # 获取DuckDB连接
    duckdb_mgr = get_duckdb()

    # 生成报告
    generator = ReportGenerator(
        db=duckdb_mgr,
        dataset_info=dataset_info,
        dashboard_config=dashboard_config,
        quality_issues=quality_issues,
    )
    report_data = await generator.generate()

    # 保存报告HTML
    report_id = str(uuid.uuid4())
    reports_dir = os.path.join(_PROJECT_ROOT, "data", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    html_path = os.path.join(reports_dir, f"{report_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(report_data["html"])

    # DB中只存章节数据，不存完整HTML（避免JSON过大）
    db_result = {k: v for k, v in report_data.items() if k != "html"}

    # 写入数据库（version管理）
    from app.models.brain import BrainTraceSummary
    version_id = str(uuid.uuid4())
    summary = BrainTraceSummary(
        run_id=report_id,
        dataset_id=primary_dataset_id,
        dashboard_id=request.dashboard_id,
        version_id=version_id,
        overall_status="completed",
        status="completed",
        completed_at=datetime.utcnow(),
        result=db_result,
    )
    db.add(summary)
    await db.commit()

    return ReportResponse(
        success=True,
        report_id=report_id,
        title=report_data["title"],
        llm_used=report_data["llm_used"],
        chart_count=report_data["chart_count"],
        generated_at=report_data["generated_at"],
        html_url=f"/api/v1/reports/{report_id}/html",
    )


@router.get("/{report_id}/html")
async def get_report_html(report_id: str):
    """获取报告HTML内容"""
    reports_dir = os.path.join(_PROJECT_ROOT, "data", "reports")
    html_path = os.path.join(reports_dir, f"{report_id}.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="报告不存在")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@router.get("/{report_id}/json")
async def get_report_json(report_id: str, db: AsyncSession = Depends(get_db)):
    """获取报告JSON数据"""
    from app.models.brain import BrainTraceSummary
    result = await db.execute(
        select(BrainTraceSummary).where(BrainTraceSummary.run_id == report_id)
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"success": True, "data": summary.result}
