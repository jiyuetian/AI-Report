"""
分享服务 - M4-04
查看/编辑权限、有效期、密码、二维码、撤销、失效页
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
import qrcode
import io
import base64
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.share import ShareLink


class ShareService:
    """分享服务"""
    
    @staticmethod
    async def create_share(
        db: AsyncSession,
        dashboard_id: str,
        permission: str = "view",  # view/edit
        expires_days: int = 7,
        password: Optional[str] = None,
        created_by: str = "anonymous"
    ) -> Dict[str, Any]:
        """创建分享链接"""
        
        # 生成短链接码
        share_code = str(uuid.uuid4())[:8]
        
        # 计算过期时间
        expires_at = datetime.utcnow() + timedelta(days=expires_days)
        
        share = ShareLink(
            id=str(uuid.uuid4()),
            dashboard_id=dashboard_id,
            share_code=share_code,
            permission=permission,
            password=password,
            expires_at=expires_at,
            created_by=created_by,
            access_count=0
        )
        
        db.add(share)
        await db.commit()
        
        # 生成二维码
        share_url = f"/s/{share_code}"
        qr_base64 = await ShareService._generate_qr(share_url)
        
        return {
            "share_id": share.id,
            "share_code": share_code,
            "share_url": share_url,
            "permission": permission,
            "expires_at": expires_at.isoformat(),
            "qr_code": qr_base64
        }
    
    @staticmethod
    async def _generate_qr(url: str) -> str:
        """生成二维码图片（Base64）"""
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_base64}"
    
    @staticmethod
    async def validate_share(
        db: AsyncSession,
        share_code: str,
        password: Optional[str] = None
    ) -> Dict[str, Any]:
        """验证分享链接"""
        
        result = await db.execute(
            select(ShareLink).where(ShareLink.share_code == share_code)
        )
        share = result.scalar_one_or_none()
        
        if not share:
            return {"valid": False, "reason": "SHARE_NOT_FOUND"}
        
        if share.status == "revoked":
            return {"valid": False, "reason": "SHARE_REVOKED"}
        
        if share.expires_at < datetime.utcnow():
            return {"valid": False, "reason": "SHARE_EXPIRED"}
        
        if share.password and share.password != password:
            return {"valid": False, "reason": "PASSWORD_REQUIRED"}
        
        # 更新访问次数
        share.access_count += 1
        await db.commit()
        
        return {
            "valid": True,
            "dashboard_id": share.dashboard_id,
            "permission": share.permission
        }
    
    @staticmethod
    async def revoke_share(
        db: AsyncSession,
        share_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """撤销分享"""
        
        result = await db.execute(
            select(ShareLink).where(ShareLink.id == share_id)
        )
        share = result.scalar_one_or_none()
        
        if not share:
            raise ValueError("分享不存在")
        
        share.status = "revoked"
        await db.commit()
        
        return {"success": True, "message": "分享已撤销"}
