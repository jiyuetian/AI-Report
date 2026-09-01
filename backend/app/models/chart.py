"""图表模型"""
from sqlalchemy import String, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.models.base import Base


class Chart(Base):
    """图表表 - 每个图表只绑一个dataset"""
    __tablename__ = "charts"
    
    # 所属看板
    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)
    
    # 数据源ID（单源绑定）- 禁止跨表计算
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    
    # 图表类型: line / bar / pie / scatter / table / kpi / funnel / radar
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # ECharts配置（JSON）
    config_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    
    # 原始查询配置（用于重新生成）
    query_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # 位置信息（JSON）
    position: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # 标题
    title: Mapped[Optional[str]] = mapped_column(String(255))
    
    # 状态: ok（正常）/ degraded（降级）/ failed（失败）/ stale（数据已过期）
    status: Mapped[str] = mapped_column(String(20), default="ok")
    
    # 排序权重
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # 关系
    dashboard = relationship("Dashboard", back_populates="charts")
    dataset = relationship("Dataset", back_populates="charts")
