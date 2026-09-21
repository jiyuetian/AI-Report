"""
分享 API - M4-04
查看/编辑权限、有效期、密码、二维码、撤销、失效页
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.share_service import ShareService

router = APIRouter(prefix="/shares", tags=["Share"])


class CreateShareRequest(BaseModel):
    """创建分享请求"""
    dashboard_id: str = Field(..., description="看板ID")
    permission: str = Field("view", description="权限: view/edit")
    expires_days: int = Field(7, description="有效期天数")
    password: Optional[str] = Field(None, description="访问密码")


class ShareVerifyRequest(BaseModel):
    """分享验证请求"""
    password: Optional[str] = Field(None, description="访问密码")


@router.post("/create")
async def create_share(
    request: CreateShareRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    创建分享链接
    
    功能：
    - 生成分享码和二维码
    - 设置权限（查看/编辑）
    - 设置有效期
    - 可选密码保护
    """
    try:
        result = await ShareService.create_share(
            db,
            dashboard_id=request.dashboard_id,
            permission=request.permission,
            expires_days=request.expires_days,
            password=request.password,
            created_by=user_id
        )
        return {
            "success": True,
            "share_id": result["share_id"],
            "share_code": result["share_code"],
            "share_url": result["share_url"],
            "permission": result["permission"],
            "expires_at": result["expires_at"],
            "qr_code": result["qr_code"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建分享失败: {str(e)}")


@router.get("/{share_code}")
async def get_share_info(
    share_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取分享信息（验证分享链接）
    
    返回看板信息，供匿名用户访问
    """
    result = await ShareService.validate_share(db, share_code)
    
    if not result["valid"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": result["reason"],
                "message": {
                    "SHARE_NOT_FOUND": "分享链接不存在",
                    "SHARE_REVOKED": "分享已被撤销",
                    "SHARE_EXPIRED": "分享已过期"
                }.get(result["reason"], "分享无效")
            }
        )
    
    return {
        "valid": True,
        "dashboard_id": result["dashboard_id"],
        "permission": result["permission"]
    }


@router.post("/{share_code}/verify")
async def verify_share_password(
    share_code: str,
    request: ShareVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """验证分享密码"""
    result = await ShareService.validate_share(db, share_code, request.password)
    
    if not result["valid"]:
        if result.get("reason") == "PASSWORD_REQUIRED":
            raise HTTPException(status_code=401, detail="需要密码访问")
        raise HTTPException(status_code=403, detail="分享无效或已过期")
    
    return {
        "valid": True,
        "dashboard_id": result["dashboard_id"],
        "permission": result["permission"]
    }


@router.post("/{share_id}/revoke")
async def revoke_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """
    撤销分享
    
    只有创建者可以撤销
    """
    try:
        result = await ShareService.revoke_share(db, share_id, user_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"撤销失败: {str(e)}")


@router.get("/my/list")
async def list_my_shares(
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取我创建的分享列表（G3：需登录）"""
    from sqlalchemy import select
    from app.models.share import ShareLink
    
    result = await db.execute(
        select(ShareLink).where(ShareLink.created_by == current_user["user_id"])
            .order_by(ShareLink.created_at.desc())
    )
    shares = result.scalars().all()
    
    return {
        "shares": [
            {
                "id": s.id,
                "share_code": s.share_code,
                "dashboard_id": s.dashboard_id,
                "permission": s.permission,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "status": s.status,
                "access_count": s.access_count,
                "has_password": s.password is not None
            }
            for s in shares
        ]
    }
