"""Prompt 中心：可编辑/版本化/启停的提示词配置表"""
from sqlalchemy import String, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from app.models.base import Base


class Prompt(Base):
    """提示词板块配置表（运行时装配的覆盖层，文件 prompts/*.md 为内置种子）"""
    __tablename__ = "prompts"

    group_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    # 覆盖内容；为 NULL 时表示"未自定义"，运行时回退到内置文件
    content: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # 1=仍与内置一致；首次自定义编辑后变 0；恢复默认后回到 1
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, default="")
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), default="")