"""数据质量模型"""
from sqlalchemy import String, Integer, ForeignKey, Text, JSON, text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from datetime import datetime
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


class ChangeLog(Base):
    """清洗修复行级变更明细（ISS-051）：每次采纳修复方案后记录字段清洗前/后快照"""
    __tablename__ = "quality_change_logs"

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    # 问题类型（与 QualityIssue.type 一致）
    issue_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # 字段名
    field_name: Mapped[Optional[str]] = mapped_column(String(100))

    # 采用的修复策略（与 fix_quality_issue 的 fix_strategy 一致）
    strategy: Mapped[Optional[str]] = mapped_column(String(30))

    # 清洗前字段统计快照（JSON：null_count / distinct_count / samples / min / max）
    before_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # 清洗后字段统计快照（JSON）
    after_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # 受影响行数（取 QualityIssue.affect_rows，权威"影响行数"）
    affected_rows: Mapped[Optional[int]] = mapped_column(Integer)


class QualityRowChange(Base):
    """清洗修复行级逐行变更明细（night45 附录 B 行级化）。

    与 ChangeLog（字段级统计快照）互补：本表逐行记录某次修复/质检发现所触及的
    原始文件行、清洗前单元格值、清洗后单元格值，支撑附录 B「原始文件行 | 字段 |
    数据问题 | 清洗策略 | 清洗前 | 清洗后」统一行级表。"""
    __tablename__ = "quality_row_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    # 阶段：apply（已执行清洗）/ detect（质检发现，待处理）
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="apply")

    # 问题类型（与 QualityIssue.type 一致：null/duplicate/format/range/...）
    issue_type: Mapped[Optional[str]] = mapped_column(String(30))

    # 字段名
    field_name: Mapped[Optional[str]] = mapped_column(String(100))

    # 采用的修复策略
    strategy: Mapped[Optional[str]] = mapped_column(String(30))

    # 原始文件行号（1-based，含表头偏移）；新数据物化 _src_row 列，老库用 rowid+2 近似
    src_row: Mapped[Optional[int]] = mapped_column(Integer)

    # 清洗前单元格值（文本化）
    before_value: Mapped[Optional[str]] = mapped_column(Text)

    # 清洗后单元格值（文本化）；待处理（detect 阶段）为 None
    after_value: Mapped[Optional[str]] = mapped_column(Text)

    # 状态：done（已修复）/ todo（待处理）/ ignored（已忽略）
    status: Mapped[str] = mapped_column(String(20), default="done")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP")
    )
