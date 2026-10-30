"""图表套路模型 - A4-②（2026-10-28）。

将「图表级套路」从 AnalysisTemplate 的 JSON 字段中独立成表，作为真正的
「图表套路库」：每个被提议/已批准的图表套路是一条记录，可独立于模板审核、
可被 match 模块按需消费。设计对齐 AnalysisTemplate 的审核状态机
（pending_review → approved / rejected），与 AI 提议、专家模板走同一审核流。
"""
from sqlalchemy import Column, String, Text, JSON, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.models.base import Base
import uuid


class ChartPattern(Base):
    """图表套路表 - 单图级可复用套路（A4-② 独立表）"""

    __tablename__ = "chart_pattern"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # 归属分析模板（审核通过后由模板落库；AI 提议未批准前可先以 template_id 关联草稿）
    template_id = Column(String(36), index=True, nullable=True,
                         comment="归属分析模板 id；未批准前为草稿关联")

    # 来源：ai（AI 提议）/ user（用户存为模板）/ expert（专家沉淀）
    source = Column(String(10), default="ai", comment="ai / user / expert")

    # 套路本体：图型 + 字段角色 + 聚合口径 + 标题线索（与 extract_chart_patterns 对齐）
    chart_type = Column(String(32), nullable=False, comment="图型 line/bar/pie/...")
    role_hint = Column(String(32), comment="字段角色 ratio/amount/count/time/metric")
    aggregation = Column(String(16), comment="聚合口径 sum/avg/mean/none")
    title_hint = Column(String(80), comment="图表标题线索（前 40 字）")
    expected_field_count = Column(Integer, default=1, comment="预期字段数（2=需维度+指标）")
    source_goal_type = Column(String(32), nullable=True, comment="来源目标类型 KPI/趋势/...")

    # 溯源证据（谁在什么时候从哪来）
    evidence = Column(JSON, nullable=True, comment="溯源证据 {theme, field_count, source_stage, ...}")

    # 审核状态机（与 AnalysisTemplate 同构）
    approved = Column(Boolean, default=False, comment="是否已被批准生效")
    status = Column(String(20), default="pending_review",
                   comment="pending_review/approved/rejected")
    reviewer = Column(String(100), nullable=True, comment="审核人")
    reviewed_at = Column(DateTime, nullable=True, comment="审核时间")
    reject_reason = Column(Text, nullable=True, comment="驳回原因")

    created_at = Column(DateTime, default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "template_id": self.template_id,
            "source": self.source,
            "chart_type": self.chart_type,
            "role_hint": self.role_hint,
            "aggregation": self.aggregation,
            "title_hint": self.title_hint,
            "expected_field_count": self.expected_field_count,
            "source_goal_type": self.source_goal_type,
            "evidence": self.evidence,
            "approved": self.approved,
            "status": self.status,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reject_reason": self.reject_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
