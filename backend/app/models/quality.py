"""数据质量模型"""
from sqlalchemy import String, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.models.base import Base


class QualityIssue(Base):
    """质量问题表 - 六类质检结果"""
    __tablename__ = "quality_issues"
    
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    
    # 字段名
    field_name: Mapped[Optional[str]] = mapped_column(String(100))
    
    # 问题类型: uniqueness（唯一性）/ null（空值）/ range（范围）/ logic（逻辑）/ code（码值）/ format（格式）
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # 严重程度: blocking（必拦）/ warning（提示）
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    
    # 状态: todo（待处理）/ done（已修复）/ ignored（已忽略）
    status: Mapped[str] = mapped_column(String(20), default="todo")
    
    # 问题描述
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 修复规则（JSON）
    fix_rule: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # 影响行数
    affect_rows: Mapped[Optional[int]] = mapped_column(Integer)
    
    # 关系
    dataset = relationship("Dataset", back_populates="quality_issues")


class CleanRule(Base):
    """清洗规则表 - 血缘层④，可撤销"""
    __tablename__ = "clean_rules"
    
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    
    # 规则类型: fill_null（填充空值）/ remove_duplicate（去重）/ format（格式化）/ filter（过滤）/ transform（转换）
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False)
    
    # 目标字段
    target_field: Mapped[Optional[str]] = mapped_column(String(100))
    
    # 规则参数（JSON）
    params: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # 是否可撤销
    reversible: Mapped[bool] = mapped_column(default=True)
    
    # 执行顺序
    execution_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # 关系
    dataset = relationship("Dataset", back_populates="clean_rules")
