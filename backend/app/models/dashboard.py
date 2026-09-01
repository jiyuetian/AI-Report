"""
看板模型 - M2-09
"""
from sqlalchemy import Column, String, DateTime, JSON, Integer, Text, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base
import uuid
from datetime import datetime


class Dashboard(Base):
    """看板表"""
    __tablename__ = "dashboards"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, comment="看板名称")
    description = Column(Text, comment="看板描述")
    
    # M5-04: 乐观锁版本号（防止并发编辑数据竞争）
    version = Column(Integer, default=1, nullable=False, comment="乐观锁版本号")
    
    # 多数据源挂载（一看板多数据源核心）
    dataset_ids = Column(JSON, default=[], comment="关联的数据集ID列表")
    primary_dataset_id = Column(String(36), comment="主数据集ID")
    
    # 看板评分
    score = Column(Integer, comment="评分卡分数")
    score_details = Column(JSON, comment="评分详情")
    passed = Column(Integer, default=0, comment="是否通过评分")
    
    # 配置
    layout = Column(JSON, default={}, comment="布局配置")
    config = Column(JSON, default={}, comment="其他配置")
    
    # 状态
    status = Column(String(20), default="draft", comment="状态: draft/published/archived")
    
    # 用户
    created_by = Column(String(50), comment="创建人")
    updated_by = Column(String(50), comment="更新人")
    
    # 时间
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    published_at = Column(DateTime)
    
    # 关系：图表（对应 chart.py 中 dashboard back_populates="charts"）
    charts = relationship("Chart", back_populates="dashboard")
    
    # 索引
    __table_args__ = (
        Index('idx_dashboard_created_by', 'created_by'),
        Index('idx_dashboard_status', 'status'),
    )
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "dataset_ids": self.dataset_ids or [],
            "primary_dataset_id": self.primary_dataset_id,
            "score": self.score,
            "score_details": self.score_details,
            "passed": self.passed,
            "layout": self.layout,
            "config": self.config,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class DashboardVersion(Base):
    """看板版本表 - M4-03 增强版"""
    __tablename__ = "dashboard_versions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id = Column(String(36), ForeignKey("dashboards.id"), nullable=False)
    version_number = Column(Integer, nullable=False, comment="版本号")
    
    # 版本标识
    name = Column(String(200), comment="版本名称")
    description = Column(Text, comment="版本描述")
    
    # 配置快照（含看板配置）
    config_snapshot = Column(JSON, comment="配置快照")
    
    # Prompt版本（策略大脑配置版本）
    prompt_version = Column(String(50), comment="Prompt版本")
    
    # 自动存档标记
    is_auto_save = Column(Integer, default=0, comment="是否自动存档: 0=否, 1=是")
    
    # 创建人
    created_by = Column(String(50))
    created_at = Column(DateTime, default=func.now())
    
    # 索引
    __table_args__ = (
        Index('idx_version_dashboard', 'dashboard_id', 'version_number'),
        Index('idx_version_auto_save', 'dashboard_id', 'is_auto_save', 'created_at'),
    )