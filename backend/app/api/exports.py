"""
导出 API - M4-05a/b
PDF/Excel/PNG 同步导出 + 水印 + 异步导出（>5s转异步，通知+7天有效）
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
import os
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.export_service import ExportService, ExportFormat
from app.models.export import ExportTask

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
    current_user: Dict = Depends(get_current_user)  # ISS-025：写操作必须登录，且以登录用户身份落账（此前任何人可匿名改）
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
            user_id=current_user["user_id"]
        )
        
        if result["mode"] == "not_implemented":
            # PDF/Excel/PNG 真实导出未实现：诚实透传，不伪造下载地址
            return {"mode": "not_implemented", "format": result["format"], "message": result["message"]}

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
    current_user: Dict = Depends(get_current_user)  # ISS-025：写操作必须登录，且以登录用户身份落账
):
    """
    异步导出（>5秒任务）
    真实创建 ExportTask 行：processing → completed/failed，落库 file_path/file_size/expire_at。
    下载链接7天有效。
    """
    try:
        format_map = {
            "pdf": ExportFormat.PDF,
            "excel": ExportFormat.EXCEL,
            "png": ExportFormat.PNG,
        }
        export_fmt = format_map.get(request.format)
        if export_fmt is None:
            # json 由 /sync 独立处理，异步导出不支持该格式
            raise HTTPException(status_code=400, detail="该格式不支持异步导出")

        # 1) 先建任务行（processing），flush 拿到真实 task.id
        task = ExportTask(
            dashboard_id=request.dashboard_id,
            fmt=request.format,
            status="processing",
            created_by=current_user["user_id"],
            expire_at=datetime.utcnow() + timedelta(days=ExportService.ASYNC_EXPIRES_DAYS),
        )
        db.add(task)
        await db.flush()

        # 2) 真实执行导出（PDF 同步生成落盘；Excel/PNG 诚实 not_implemented）
        result = await ExportService.export_dashboard(
            db,
            dashboard_id=request.dashboard_id,
            format=export_fmt,
            include_watermark=request.include_watermark,
            include_logic=request.include_logic,
            user_id=current_user["user_id"],
        )

        # 3) 据真实结果更新任务行（绝不编造假值）
        dl = result.get("download_url", "")
        if result.get("mode") == "sync":
            fname = dl.rsplit("/", 1)[-1] if dl else f"export_{request.dashboard_id}.pdf"
            backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            task.status = "completed"
            task.file_path = os.path.join(backend_root, "data", "exports", fname)
            task.file_size = result.get("file_size", 0)
        elif result.get("mode") == "not_implemented":
            task.status = "failed"
            task.error_msg = result.get("message", f"{request.format} 导出功能暂未实现")
        else:
            task.status = "failed"
            task.error_msg = "导出返回未知模式"

        await db.commit()
        await db.refresh(task)

        return {
            "mode": "async",
            "task_id": task.id,
            "status": task.status,
            "message": "导出任务已创建并处理，可通过 /exports/status/{task_id} 查询",
            "check_status_url": f"/api/v1/exports/status/{task.id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建导出任务失败: {str(e)}")


@router.get("/status/{task_id}")
async def get_export_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """查询导出任务状态（查真实 export_tasks 表，限本人或管理员）"""
    row = (await db.execute(
        select(ExportTask).where(ExportTask.id == task_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    # 归属校验：仅本人或管理员可见，避免向他人泄露任务存在性
    is_admin = bool(current_user.get("is_superuser")) or ("admin" in (current_user.get("roles") or []))
    if not is_admin and row.created_by != current_user.get("user_id"):
        raise HTTPException(status_code=404, detail="导出任务不存在")
    download_url = f"/downloads/{os.path.basename(row.file_path)}" if row.file_path else None
    return {
        "task_id": row.id,
        "dashboard_id": row.dashboard_id,
        "format": row.fmt,
        "status": row.status,
        "progress": 100 if row.status == "completed" else (0 if row.status in ("pending", "processing") else 50),
        "download_url": download_url,
        "file_size": row.file_size or 0,
        "expires_at": row.expire_at.isoformat() if row.expire_at else None,
        "error_msg": row.error_msg,
    }


@router.get("/my/list")
async def list_my_exports(
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取我的导出历史（查真实 export_tasks 表，无则空列表）"""
    rows = (await db.execute(
        select(ExportTask)
        .where(ExportTask.created_by == current_user["user_id"])
        .order_by(ExportTask.created_at.desc())
    )).scalars().all()
    items = []
    for row in rows:
        download_url = None
        if row.file_path and row.status == "completed":
            download_url = f"/downloads/{os.path.basename(row.file_path)}"
        items.append({
            "id": row.id,
            "dashboard_id": row.dashboard_id,
            "format": row.fmt,
            "status": row.status,
            "download_url": download_url,
            "file_size": row.file_size or 0,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expire_at.isoformat() if row.expire_at else None,
            "error_msg": row.error_msg,
        })
    return {"exports": items, "total": len(items)}
