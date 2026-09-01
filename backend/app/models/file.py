"""文件模型"""
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import datetime
from app.models.base import Base


class File(Base):
    """文件表 - 用户上传的原始文件"""
    __tablename__ = "files"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 文件指纹，用于重复检测
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # 文件大小（字节）
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # 存储路径
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # 状态: temporary（临时）/ archived（归档）/ deleted（已删除）
    status: Mapped[str] = mapped_column(String(20), default="temporary")
    
    # 过期时间（临时文件定期清理）
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # 上传者
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100))
    
    # 关系
    datasets = relationship("Dataset", back_populates="file")
