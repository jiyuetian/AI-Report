"""
Token加量申请API - M3-06
用户申请→管理员审批→当日有效
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, update
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.chat import TokenQuota, TokenApplication

router = APIRouter(prefix="/tokens/applications", tags=["Token加量申请"])


# 管理员权限检查
async def require_admin(current_user: str = "anonymous"):
    """检查是否为管理员"""
    admin_users = ["admin", "administrator", "system"]
    if current_user not in admin_users and not current_user.startswith("admin_"):
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "需要管理员权限"}
        )
    return current_user


# ============== 请求/响应模型 ==============

class ApplyQuotaRequest(BaseModel):
    """申请加量请求"""
    amount: int = Field(..., ge=500, le=10000, description="申请数量")
    reason: str = Field(..., min_length=10, max_length=500, description="申请理由")


class ApproveQuotaRequest(BaseModel):
    """审批加量请求"""
    approved_amount: int = Field(..., ge=0, le=10000, description="批准数量")
    comment: Optional[str] = Field("", description="审批备注")


class ApplicationResponse(BaseModel):
    """申请响应"""
    id: str
    user_id: str
    apply_amount: int
    apply_reason: str
    status: str
    approved_by: Optional[str]
    approved_amount: Optional[int]
    created_at: str


# ============== API端点 ==============

@router.post("/apply", response_model=Dict)
async def apply_for_extra_quota(
    request: ApplyQuotaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    用户申请Token加量
    
    创建加量申请，等待管理员审批
    """
    # 检查是否有待审批的申请
    result = await db.execute(
        select(TokenApplication)
        .where(
            and_(
                TokenApplication.user_id == current_user,
                TokenApplication.status == "pending"
            )
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        return {
            "success": False,
            "code": "EXISTING_APPLICATION",
            "message": "您有正在审批中的申请，请勿重复提交",
            "existing_application": existing.to_dict()
        }
    
    # 创建申请
    application = TokenApplication(
        user_id=current_user,
        apply_amount=request.amount,
        apply_reason=request.reason,
        status="pending"
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    
    return {
        "success": True,
        "message": "加量申请已提交，等待管理员审批",
        "application": application.to_dict(),
        "notice": "审批通过后当日有效"
    }


@router.get("/my-applications", response_model=Dict)
async def get_my_applications(
    status: Optional[str] = None,  # pending/approved/rejected
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """获取我的加量申请列表"""
    query = select(TokenApplication).where(
        TokenApplication.user_id == current_user
    )
    
    if status:
        query = query.where(TokenApplication.status == status)
    
    query = query.order_by(desc(TokenApplication.created_at)).limit(limit)
    
    result = await db.execute(query)
    applications = result.scalars().all()
    
    return {
        "success": True,
        "count": len(applications),
        "applications": [a.to_dict() for a in applications]
    }


@router.get("/my-applications/{application_id}", response_model=Dict)
async def get_application_detail(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """获取申请详情"""
    result = await db.execute(
        select(TokenApplication)
        .where(
            and_(
                TokenApplication.id == application_id,
                TokenApplication.user_id == current_user
            )
        )
    )
    application = result.scalar_one_or_none()
    
    if not application:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "申请不存在"}
        )
    
    return {
        "success": True,
        "application": application.to_dict()
    }


# ============== 管理员接口 ==============

@router.get("/admin/pending", response_model=Dict)
async def get_pending_applications(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin)
):
    """管理员获取待审批列表"""
    result = await db.execute(
        select(TokenApplication)
        .where(TokenApplication.status == "pending")
        .order_by(desc(TokenApplication.created_at))
        .limit(limit)
    )
    applications = result.scalars().all()
    
    return {
        "success": True,
        "count": len(applications),
        "pending_count": len(applications),
        "applications": [a.to_dict() for a in applications]
    }


@router.post("/admin/{application_id}/approve", response_model=Dict)
async def approve_application(
    application_id: str,
    request: ApproveQuotaRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: str = Depends(require_admin)
):
    """
    管理员审批通过
    
    审批后当日有效
    """
    result = await db.execute(
        select(TokenApplication).where(TokenApplication.id == application_id)
    )
    application = result.scalar_one_or_none()
    
    if not application:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "申请不存在"}
        )
    
    if application.status != "pending":
        return {
            "success": False,
            "message": f"申请状态为{application.status}，无法审批",
            "current_status": application.status
        }
    
    # 计算过期时间（当日24:00）
    now = datetime.now()
    expires_at = now.replace(hour=23, minute=59, second=59)
    
    # 更新申请
    application.status = "approved"
    application.approved_by = admin_user
    application.approved_amount = request.approved_amount
    application.approve_comment = request.comment
    application.expires_at = expires_at
    
    # 更新用户配额
    quota_result = await db.execute(
        select(TokenQuota).where(TokenQuota.user_id == application.user_id)
    )
    quota = quota_result.scalar_one_or_none()
    
    if quota:
        quota.extra_quota = (quota.extra_quota or 0) + request.approved_amount
        quota.remaining = quota.daily_limit + quota.extra_quota - quota.used_today
    else:
        # 创建新配额记录
        quota = TokenQuota(
            user_id=application.user_id,
            daily_limit=5000,
            used_today=0,
            extra_quota=request.approved_amount,
            remaining=5000 + request.approved_amount
        )
        db.add(quota)
    
    await db.commit()
    await db.refresh(application)
    await db.refresh(quota)
    
    return {
        "success": True,
        "message": f"已批准增加{request.approved_amount}Token",
        "application": application.to_dict(),
        "quota_after": quota.to_dict(),
        "expires_at": expires_at.isoformat(),
        "notice": "加量当日有效"
    }


@router.post("/admin/{application_id}/reject", response_model=Dict)
async def reject_application(
    application_id: str,
    comment: str = "",
    db: AsyncSession = Depends(get_db),
    admin_user: str = Depends(require_admin)
):
    """管理员拒绝申请"""
    result = await db.execute(
        select(TokenApplication).where(TokenApplication.id == application_id)
    )
    application = result.scalar_one_or_none()
    
    if not application:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "申请不存在"}
        )
    
    if application.status != "pending":
        return {
            "success": False,
            "message": f"申请状态为{application.status}，无法拒绝",
            "current_status": application.status
        }
    
    application.status = "rejected"
    application.approved_by = admin_user
    application.approve_comment = comment
    
    await db.commit()
    await db.refresh(application)
    
    return {
        "success": True,
        "message": "申请已拒绝",
        "application": application.to_dict()
    }


@router.get("/admin/all", response_model=Dict)
async def get_all_applications(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin)
):
    """管理员获取全部申请列表"""
    query = select(TokenApplication)
    
    if status:
        query = query.where(TokenApplication.status == status)
    
    query = query.order_by(desc(TokenApplication.created_at)).limit(limit)
    
    result = await db.execute(query)
    applications = result.scalars().all()
    
    # 统计
    stats_result = await db.execute(
        select(TokenApplication.status, TokenApplication.id)
    )
    all_apps = stats_result.all()
    stats = {
        "pending": sum(1 for a in all_apps if a.status == "pending"),
        "approved": sum(1 for a in all_apps if a.status == "approved"),
        "rejected": sum(1 for a in all_apps if a.status == "rejected")
    }
    
    return {
        "success": True,
        "count": len(applications),
        "statistics": stats,
        "applications": [a.to_dict() for a in applications]
    }


# ============== 检查状态 ==============

@router.get("/check-active", response_model=Dict)
async def check_active_extra_quota(
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """检查当前有效的加量"""
    result = await db.execute(
        select(TokenQuota).where(TokenQuota.user_id == current_user)
    )
    quota = result.scalar_one_or_none()
    
    if not quota or not quota.extra_quota:
        return {
            "success": True,
            "has_active": False,
            "extra_quota": 0
        }
    
    return {
        "success": True,
        "has_active": quota.extra_quota > 0,
        "extra_quota": quota.extra_quota,
        "total_limit": quota.daily_limit + quota.extra_quota,
        "used_today": quota.used_today,
        "remaining": quota.remaining
    }