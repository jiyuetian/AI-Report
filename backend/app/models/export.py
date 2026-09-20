"""导出模型"""
from sqlalchemy import String, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import datetime
from app.models.base import Base


class ExportTask(Base):
    """导出任务表"""
    __tablename__ = "export_tasks"
    
    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)
    
    # 格式: pdf / png / excel / ppt
    fmt: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # 状态: pending（待处理）/ processing（处理中）/ completed（已完成）/ failed（失败）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    
    # 文件路径
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    
    # 文件大小
    file_size: Mapped[Optional[int]] = mapped_column(default=0)
    
    # 过期时间（7天有效）
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # 错误信息
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    
    # 创建者
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
