"""分享模型"""
from sqlalchemy import String, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import datetime
from app.models.base import Base


class ShareLink(Base):
    """分享链接表"""
    __tablename__ = "share_links"
    
    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)
    
    # 访问权限: view（仅查看）/ edit（可编辑）
    perm: Mapped[str] = mapped_column(String(20), default="view")
    
    # 过期时间
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # 访问密码（可选）
    password: Mapped[Optional[str]] = mapped_column(String(100))
    
    # 是否已撤销
    revoked: Mapped[bool] = mapped_column(default=False)
    
    # 访问次数
    access_count: Mapped[int] = mapped_column(default=0)
    
    # 创建者
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
