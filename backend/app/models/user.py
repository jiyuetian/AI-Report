"""用户和权限模型"""
from sqlalchemy import String, Integer, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign
from typing import Optional, List
from datetime import datetime
from app.models.base import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(100))
    
    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Token配额
    token_quota: Mapped[int] = mapped_column(Integer, default=5000)  # 每日默认5000 tokens
    
    # 时间戳
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # 关系
    roles: Mapped[List["Role"]] = relationship("Role", secondary="user_roles", back_populates="users")
    dashboards: Mapped[List["Dashboard"]] = relationship(
        "Dashboard",
        primaryjoin="User.username == foreign(Dashboard.created_by)",
        viewonly=True,
    )
    chat_sessions: Mapped[List["ChatSession"]] = relationship(
        "ChatSession",
        primaryjoin="User.id == foreign(ChatSession.user_id)",
        viewonly=True,
    )


class Role(Base):
    """角色表"""
    __tablename__ = "roles"
    
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # 默认配额
    default_quota: Mapped[int] = mapped_column(Integer, default=5000)
    
    # 权限（JSON存储）
    permissions: Mapped[Optional[str]] = mapped_column(Text)  # JSON格式
    
    # 关系
    users: Mapped[List["User"]] = relationship("User", secondary="user_roles", back_populates="roles")


class UserRole(Base):
    """用户角色关联表"""
    __tablename__ = "user_roles"
    
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
