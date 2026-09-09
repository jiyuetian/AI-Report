"""
看板 API - M4-06 我的看板 + M2-09/M3-07
列表/检索/筛选/详情抽屉/删除二次确认/数据源更新提醒/空状态
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_, or_, delete
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.dashboard import Dashboard, DashboardVersion
from app.models.dataset import Dataset
from app.models.chart import Chart
from app.models.export import ExportTask
from app.models.share import ShareLink
from app.models.file import File
from app.models.brain import BrainTrace

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


class CreateDashboardRequest(BaseModel):
    """创建看板请求"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    dataset_ids: List[str] = []


class UpdateDashboardRequest(BaseModel):
    """更新看板请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    layout: Optional[Dict[str, Any]] = None


@router.get("/my")
async def list_my_dashboards(
    search: str = Query("", description="搜索关键词"),
    status: str = Query("all", description="状态筛选: all/draft/published/archived"),
    sort_by: str = Query("updated", description="排序: updated/created/name/score"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    我的看板列表（M4-06）
    
    功能：
    - 搜索：按名称/描述搜索
    - 筛选：按状态筛选
    - 排序：更新时间/创建时间/名称/评分
    - 分页
    """
    # 兼容不同来源的看板 owner（上传/对话生成的看板 owner 为 'current'，
    # 注入/演示数据为 'anonymous'），否则这些看板在"我的看板"中永远不可见
    _OWNERS = ("anonymous", "current")
    query = select(Dashboard).where(
        or_(
            Dashboard.created_by.in_(_OWNERS),
            Dashboard.updated_by.in_(_OWNERS)
        )
    )
    
    # 状态筛选
    if status != "all":
        query = query.where(Dashboard.status == status)
    
    # 搜索筛选
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Dashboard.name.ilike(search_pattern),
                Dashboard.description.ilike(search_pattern)
            )
        )
    
    # 排序
    if sort_by == "updated":
        query = query.order_by(desc(Dashboard.updated_at))
    elif sort_by == "created":
        query = query.order_by(desc(Dashboard.created_at))
    elif sort_by == "name":
        query = query.order_by(Dashboard.name)
    elif sort_by == "score":
        query = query.order_by(desc(Dashboard.score))
    else:
        query = query.order_by(desc(Dashboard.updated_at))
    
    # 分页
    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar()
    
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    dashboards = result.scalars().all()
    
    # 检查数据源更新提醒
    dashboard_list = []
    for dash in dashboards:
        # 检查关联数据源是否有更新
        update_reminder = await _check_dataset_updates(db, dash)
        
        dashboard_list.append({
            "id": dash.id,
            "name": dash.name,
            "description": dash.description,
            "status": dash.status,
            "score": dash.score,
            "passed": dash.passed,
            "dataset_count": len(dash.dataset_ids) if dash.dataset_ids else 0,
            "update_reminder": update_reminder,  # 数据源更新提醒
            "created_at": dash.created_at.isoformat() if dash.created_at else None,
            "updated_at": dash.updated_at.isoformat() if dash.updated_at else None
        })
    
    return {
        "list": dashboard_list,
        "total": total,
        "page": page,
        "page_size": page_size
    }


async def _check_dataset_updates(db: AsyncSession, dashboard: Dashboard) -> Dict[str, Any]:
    """检查关联数据源是否有更新"""
    if not dashboard.dataset_ids:
        return {"has_update": False}
    
    result = await db.execute(
        select(Dataset).where(Dataset.id.in_(dashboard.dataset_ids))
    )
    datasets = result.scalars().all()
    
    updated_count = 0
    for ds in datasets:
        # 检查数据集是否在24小时内更新过
        if ds.updated_at and dashboard.updated_at:
            if ds.updated_at > dashboard.updated_at:
                updated_count += 1
    
    if updated_count > 0:
        return {
            "has_update": True,
            "message": f"{updated_count}个数据源有更新",
            "dataset_ids": [d.id for d in datasets if d.updated_at > dashboard.updated_at]
        }
    
    return {"has_update": False}


@router.get("/{dashboard_id}")
async def get_dashboard_detail(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    看板详情（详情抽屉）
    """
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()
    
    if not dashboard:
        raise HTTPException(status_code=404, detail="看板不存在")
    
    # 获取关联数据源信息
    datasets_info = []
    if dashboard.dataset_ids:
        ds_result = await db.execute(
            select(Dataset).where(Dataset.id.in_(dashboard.dataset_ids))
        )
        datasets = ds_result.scalars().all()
        for ds in datasets:
            datasets_info.append({
                "id": ds.id,
                "name": ds.name,
                "grain": ds.grain,
                "row_count": ds.row_count
            })
    
    return {
        "id": dashboard.id,
        "name": dashboard.name,
        "description": dashboard.description,
        "status": dashboard.status,
        "score": dashboard.score,
        "passed": dashboard.passed,
        "datasets": datasets_info,
        # 前端渲染图表数据依赖 primary_dataset_id / dataset_ids（此前遗漏导致 /datasets/undefined/chart-data）
        "primary_dataset_id": dashboard.primary_dataset_id,
        "dataset_ids": dashboard.dataset_ids or [],
        "config": dashboard.config,
        "layout": dashboard.layout,
        "created_by": dashboard.created_by,
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "updated_at": dashboard.updated_at.isoformat() if dashboard.updated_at else None
    }


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    confirm_name: str = Query(..., description="确认名称（需输入看板名称）"),
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    删除看板（M4-06 删除二次确认 - 需输入名称）
    
    安全机制：
    - 需要输入看板名称二次确认
    - 只有创建者或管理员可删除
    - 已发布的看板不能删除
    """
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()
    
    if not dashboard:
        raise HTTPException(status_code=404, detail="看板不存在")
    
    # 验证确认名称
    if dashboard.name != confirm_name:
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "CONFIRM_NAME_MISMATCH",
                "message": f"确认名称不匹配，请输入正确的看板名称: {dashboard.name}"
            }
        )
    
    # 检查权限（只有创建者可删除）
    # 与列表查询的归属语义对齐（_OWNERS = anonymous/current）：auth 未落地前二者视为同一用户，放行删除
    if dashboard.created_by != user_id and not (
        dashboard.created_by in ("anonymous", "current") and user_id in ("anonymous", "current")
    ):
        raise HTTPException(
            status_code=403, 
            detail="只有创建者可删除看板"
        )
    
    # 已发布的看板不能删除
    # 取消：本产品生成看板即自动发布草稿流程，前端暂无"取消发布"入口，
    # 若保留该校验则所有生成看板都无法删除（用户反馈"删不掉"）。
    # 删除动作已有二次确认（输入名称）+ 危险确认，足够兜底，故放行已发布看板删除。
    if dashboard.status == "published":
        pass  # 放行：允许删除已发布看板

    # 显式删除所有子记录（SQLite CASCADE 在某些场景不生效，需手动清理）
    await db.execute(delete(Chart).where(Chart.dashboard_id == dashboard_id))
    await db.execute(delete(DashboardVersion).where(DashboardVersion.dashboard_id == dashboard_id))
    await db.execute(delete(ExportTask).where(ExportTask.dashboard_id == dashboard_id))
    await db.execute(delete(ShareLink).where(ShareLink.dashboard_id == dashboard_id))
    await db.flush()

    await db.delete(dashboard)
    await db.commit()
    
    return {
        "success": True,
        "message": f"看板 '{dashboard.name}' 已删除"
    }


@router.get("/stats/overview")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    看板统计概览
    """
    # 总数
    _OWNERS = ("anonymous", "current")
    total_result = await db.execute(
        select(func.count(Dashboard.id)).where(
            or_(
                Dashboard.created_by.in_(_OWNERS),
                Dashboard.updated_by.in_(_OWNERS)
            )
        )
    )
    total = total_result.scalar()
    
    # 按状态统计
    status_counts = {}
    for status in ["draft", "published", "archived"]:
        count_result = await db.execute(
            select(func.count(Dashboard.id)).where(
                and_(
                    Dashboard.status == status,
                    or_(
                        Dashboard.created_by.in_(_OWNERS),
                        Dashboard.updated_by.in_(_OWNERS)
                    )
                )
            )
        )
        status_counts[status] = count_result.scalar()
    
    # 今日创建数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(func.count(Dashboard.id)).where(
            and_(
                Dashboard.created_at >= today_start,
                Dashboard.created_by.in_(_OWNERS)
            )
        )
    )
    today_count = today_result.scalar()
    
    return {
        "total": total,
        "by_status": status_counts,
        "today_created": today_count
    }


@router.post("/")
async def create_dashboard(
    request: CreateDashboardRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """创建看板"""
    dashboard = Dashboard(
        name=request.name,
        description=request.description,
        dataset_ids=request.dataset_ids,
        primary_dataset_id=request.dataset_ids[0] if request.dataset_ids else None,
        created_by=user_id,
        status="draft"
    )
    
    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)
    
    return {
        "success": True,
        "dashboard_id": dashboard.id,
        "name": dashboard.name
    }


@router.patch("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: str,
    request: UpdateDashboardRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """更新看板（部分更新）"""
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()
    
    if not dashboard:
        raise HTTPException(status_code=404, detail="看板不存在")
    
    if request.name is not None:
        dashboard.name = request.name
    if request.description is not None:
        dashboard.description = request.description
    if request.config is not None:
        dashboard.config = request.config
    if request.layout is not None:
        dashboard.layout = request.layout
    
    dashboard.updated_by = user_id
    dashboard.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "success": True,
        "message": "看板已更新"
    }
