"""配额模型"""
from sqlalchemy import String, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import date
from app.models.base import Base


class QuotaUsage(Base):
    """配额使用表 - 日重置"""
    __tablename__ = "quota_usage"
    
    user_id: Mapped[str] = mapped_column(String(100), primary_key=True, nullable=False)
    
    # 日期
    date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    
    # 已使用Token数
    used_tokens: Mapped[int] = mapped_column(Integer, default=0)
