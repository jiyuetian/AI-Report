"""
分析模板库模型 - 2.6 P0
analysis_template: 跨数据集复用的分析目标模板（按字段画像特征匹配，不绑列名）

与 brain.py 的 Base/Column 约定对齐：
- 主键 String(36) + uuid4 默认
- 时间列 DateTime + func.now() server_default / onupdate
- JSON 列用 sqlalchemy.JSON
"""
from sqlalchemy import Column, String, Text, JSON, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from app.models.base import Base
import uuid


class AnalysisTemplate(Base):
    """分析模板表 - 跨数据集复用，命中 approved 模板即并入 S2 候选目标

    A4-②/③（2026-10-28 大改）：
    - chart_patterns：图表级套路（独立于 base_goals，粒度下沉到单图），落库持久化。
    - status：审核状态机 pending_review → approved / rejected；与 approved 同步。
    - reviewer / reviewed_at / reject_reason：审核留痕。
    - source 扩展为 system / user / expert / ai，四类提议走同一审核流。
    """

    __tablename__ = "analysis_template"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False, comment="展示名，如：担保风控·标准六图")
    description = Column(Text, comment="模板说明")

    # 意图骨架：用字段画像特征描述模板的「目标结构」，不绑具体列名
    # 形如 [{"type":"KPI","role_hint":"金额指标","title":"总担保金额"}, ...]
    goal_skeleton = Column(JSON, comment="目标骨架（按 cardinality/business_role/recommended_agg 设计，非列名）")

    # 匹配特征：与数据集 profile 做特征交集打分用的条件
    # 形如 {"must_have_types":["CATEGORY","NUMBER"],"semantic_hints":["比率类","金额指标"],
    #       "min_fields":4,"theme_hint":"担保|风控","cardinality_need":["high"]}
    match_features = Column(JSON, comment="匹配条件（字段画像特征，不绑列名）")

    # 预置目标：对齐 AnalysisGoal.to_dict() 结构，命中后并入 S2 候选
    base_goals = Column(JSON, comment="预置分析目标（对齐 AnalysisGoal）")

    # A4-②：图表级套路（粒度下沉到单图），持久化落库（此前仅暂存于候选返回值）
    chart_patterns = Column(JSON, comment="图表级套路列表（A4-② 独立字段，可落库持久化）")

    # A4-③：审核状态机（与 approved 同步）。pending_review → approved / rejected
    status = Column(String(20), default="pending_review",
                    comment="审核状态：pending_review/approved/rejected")
    reviewer = Column(String(100), nullable=True, comment="审核人（user_id/用户名）")
    reviewed_at = Column(DateTime, nullable=True, comment="审核时间")
    reject_reason = Column(Text, nullable=True, comment="驳回原因（驳回时填写）")

    approved = Column(Boolean, default=False, comment="须经用户确认才生效；未确认不套用")
    usage_count = Column(Integer, default=0, comment="被命中套用次数")
    source = Column(String(10), default="system", comment="system / user / expert / ai")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "goal_skeleton": self.goal_skeleton,
            "match_features": self.match_features,
            "base_goals": self.base_goals,
            "chart_patterns": self.chart_patterns,
            "status": self.status,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reject_reason": self.reject_reason,
            "approved": self.approved,
            "usage_count": self.usage_count,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
