"""数据集模型"""
from sqlalchemy import String, Integer, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.models.base import Base


class Dataset(Base):
    """数据集表 - 一看板多数据源的核心实体"""
    __tablename__ = "datasets"
    
    # 数据集名称
    name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # 关联文件
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    
    # DuckDB表名
    duckdb_table: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # 数据粒度: row（单笔）/ customer（客户级）/ month_agg（月度汇总）/ custom（自定义）
    grain: Mapped[str] = mapped_column(String(20), default="row")
    
    # Schema信息（JSON存储字段列表）
    schema_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # 字段画像（统计信息）
    profile_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # 数据质量分数（0-100）
    quality_score: Mapped[Optional[int]] = mapped_column(Integer)
    
    # 行数
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 状态: pending（待处理）/ processing（处理中）/ ready（就绪）/ failed（失败）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    
    # 关系
    file = relationship("File", back_populates="datasets")
    quality_issues = relationship("QualityIssue", back_populates="dataset")
    clean_rules = relationship("CleanRule", back_populates="dataset")
    charts = relationship("Chart", back_populates="dataset")
