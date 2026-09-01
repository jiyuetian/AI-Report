"""审计模型"""
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.base import Base


class AuditLog(Base):
    """审计日志表 - 加密存储"""
    __tablename__ = "audit_logs"
    
    # 用户
    user: Mapped[Optional[str]] = mapped_column(String(100))
    
    # 动作: login / logout / upload / analyze / export / share / delete
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # 操作对象类型
    object_type: Mapped[Optional[str]] = mapped_column(String(50))
    
    # 操作对象ID
    object_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # IP地址
    ip: Mapped[Optional[str]] = mapped_column(String(50))
    
    # 结果: success / failure
    result: Mapped[str] = mapped_column(String(20), default="success")
    
    # 详细信息（JSON）
    detail_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
