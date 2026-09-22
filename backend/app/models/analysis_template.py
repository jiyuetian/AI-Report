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
    """分析模板表 - 跨数据集复用，命中 approved 模板即并入 S2 候选目标"""

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

    approved = Column(Boolean, default=False, comment="须经用户确认才生效；未确认不套用")
    usage_count = Column(Integer, default=0, comment="被命中套用次数")
    source = Column(String(10), default="system", comment="system / user / ai")

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
            "approved": self.approved,
            "usage_count": self.usage_count,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
