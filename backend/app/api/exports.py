"""
导出 API - M4-05a/b
PDF/Excel/PNG 同步导出 + 水印 + 异步导出（>5s转异步，通知+7天有效）
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.export_service import ExportService, ExportFormat

router = APIRouter(prefix="/exports", tags=["Exports"])


class ExportRequest(BaseModel):
    """导出请求"""
    dashboard_id: str = Field(..., description="看板ID")
    format: Literal["pdf", "excel", "png", "json"] = Field(..., description="导出格式")
    include_watermark: bool = Field(True, description="是否包含水印")
    include_logic: bool = Field(False, description="是否包含口径说明")
    include_data: bool = Field(False, description="是否包含数据")


class AsyncExportResponse(BaseModel):
    """异步导出响应"""
    mode: str = "async"
    task_id: str
    message: str
    check_status_url: str


@router.post("/sync")
async def export_sync(
    request: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    同步导出（<5秒返回）
    
    支持格式：PDF、Excel、PNG、JSON
    可选：水印、口径说明、包含数据
    """
    try:
        # JSON 导出：真实返回看板配置内容，供前端触发下载（修复 json→excel 误映射）
        if request.format == "json":
            from sqlalchemy import select
            from app.models.dashboard import Dashboard
            result = await db.execute(select(Dashboard).where(Dashboard.id == request.dashboard_id))
            dash = result.scalar_one_or_none()
            if not dash:
                raise HTTPException(status_code=404, detail="看板不存在")
            payload = {
                "dashboard_id": dash.id,
                "name": dash.name,
                "description": dash.description,
                "status": dash.status,
                "config": dash.config if hasattr(dash, "config") else {},
                "exported_at": datetime.utcnow().isoformat(),
            }
            return {
                "mode": "sync",
                "format": "json",
                "filename": f"{dash.name}.dashboard.json",
                "content": payload,
            }

        format_map = {
            "pdf": ExportFormat.PDF,
            "excel": ExportFormat.EXCEL,
            "png": ExportFormat.PNG
        }
        
        result = await ExportService.export_dashboard(
            db,
            dashboard_id=request.dashboard_id,
            format=format_map[request.format],
            include_watermark=request.include_watermark,
            include_logic=request.include_logic,
            user_id=user_id
        )
        
        if result["mode"] == "async":
            # 超时转异步
            return AsyncExportResponse(**result)
        
        # 同步返回
        return {
            "mode": "sync",
            "format": request.format,
            "download_url": result["download_url"],
            "file_size": result["file_size"],
            "generated_at": result["generated_at"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/async")
async def export_async(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    异步导出（>5秒任务）
    
    直接创建后台任务，通过通知中心返回结果
    下载链接7天有效
    """
    try:
        format_map = {
            "pdf": ExportFormat.PDF,
            "excel": ExportFormat.EXCEL,
            "png": ExportFormat.PNG
        }
        
        result = await ExportService.export_dashboard(
            db,
            dashboard_id=request.dashboard_id,
            format=format_map[request.format],
            include_watermark=request.include_watermark,
            include_logic=request.include_logic,
            user_id=user_id
        )
        
        return {
            "mode": "async",
            "task_id": result.get("task_id", "task_001"),
            "message": "导出任务已创建，将通过通知中心告知结果",
            "check_status_url": f"/api/v1/exports/status/{result.get('task_id', 'task_001')}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建导出任务失败: {str(e)}")


@router.get("/status/{task_id}")
async def get_export_status(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """查询导出任务状态"""
    # 模拟状态查询
    return {
        "task_id": task_id,
        "status": "completed",  # pending/running/completed/failed
        "progress": 100,
        "download_url": f"/downloads/export_{task_id}.pdf",
        "expires_at": "2026-08-27T14:00:00Z",  # 7天后过期
        "file_size": 1024 * 1024
    }


@router.get("/my/list")
async def list_my_exports(
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """获取我的导出历史"""
    return {
        "exports": [
            {
                "id": "exp_001",
                "dashboard_id": "dash_001",
                "format": "pdf",
                "status": "completed",
                "download_url": "/downloads/export_001.pdf",
                "created_at": "2026-08-20T10:00:00Z",
                "expires_at": "2026-08-27T10:00:00Z"
            }
        ]
    }
