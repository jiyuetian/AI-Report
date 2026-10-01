"""
图表模板库模型 - night14 Task B
chart_template: 跨看板复用的图表组合模板（按业务域预置，一键套用到目标看板）。

设计要点（呼应分析模板 analysis_template 的约定，但更轻）：
- 主键 String(36) + uuid4 默认
- 时间列 DateTime + func.now() server_default / onupdate
- JSON 列用 sqlalchemy.JSON
- config_json 形如 {"charts":[{"chart_type","title","metric_field","dimension_field","aggregation"}...]}
  字段名是「候选名」：套用时由 apply 端点按目标数据集真实字段画像精确/子串匹配，
  命不中则跳过该图（不臆造垃圾图，复用电 executor 的严格匹配护栏）。
- tags 为业务标签数组（JSON），便于前端按业务域检索。
- source: system(预置) / user(用户自建)。
"""
from sqlalchemy import Column, String, Text, JSON, Integer, DateTime
from sqlalchemy.sql import func
from app.models.base import Base
import uuid


class ChartTemplate(Base):
    """图表模板表 - 跨看板复用的图表组合模板"""

    __tablename__ = "chart_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False, comment="模板展示名，如：担保风控·标准四图")
    category = Column(String(40), nullable=False, index=True, comment="业务域，如：担保风控/信贷/财务")
    description = Column(Text, comment="模板说明")

    # 图表组合：对齐 executor._execute_add_chart 的 charts spec 结构
    # 形如 {"charts":[{"chart_type":"bar","title":"区域担保余额","dimension_field":"区域",
    #        "metric_field":"担保余额","aggregation":"sum"}, ...]}
    config_json = Column(JSON, nullable=False, comment="图表组合配置（候选字段名，套用按真实字段映射）")

    # 业务标签数组
    tags = Column(JSON, comment="业务标签数组，如 ['风控','余额','区域']")

    source = Column(String(10), default="system", comment="system / user")
    usage_count = Column(Integer, default=0, comment="被套用次数")
    created_by = Column(String(50), comment="创建人(user 自建时填)")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "config_json": self.config_json,
            "tags": self.tags or [],
            "source": self.source,
            "usage_count": self.usage_count or 0,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
