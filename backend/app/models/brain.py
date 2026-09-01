"""
策略大脑模型 - M2-01
brain_configs: 配置存储+版本+热更新+回滚
brain_traces: 五阶段全链路trace落库
"""
from sqlalchemy import Column, String, DateTime, JSON, Integer, Text, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base
import uuid
from datetime import datetime


class BrainConfig(Base):
    """策略大脑配置表 - 支持版本管理和热更新"""
    __tablename__ = "brain_configs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_key = Column(String(100), nullable=False, comment="配置键，如: theme_dict, goal_prompt, chart_rules")
    category = Column(String(50), nullable=False, comment="配置类别: theme/goal/chart/orchestrate/score")
    version = Column(Integer, nullable=False, default=1, comment="版本号，递增")
    content = Column(JSON, nullable=False, comment="配置内容")
    description = Column(Text, comment="配置说明")
    is_active = Column(Integer, default=1, comment="是否当前生效版本: 1=生效, 0=历史")
    created_by = Column(String(50), comment="创建人")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 索引
    __table_args__ = (
        Index('idx_config_key_active', 'config_key', 'is_active'),
        Index('idx_category_version', 'category', 'version'),
    )
    
    def to_dict(self):
        return {
            "id": self.id,
            "config_key": self.config_key,
            "category": self.category,
            "version": self.version,
            "content": self.content,
            "description": self.description,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class BrainTrace(Base):
    """策略大脑执行trace表 - 五阶段全链路落库"""
    __tablename__ = "brain_traces"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), nullable=False, index=True, comment="运行ID，关联一次完整的brain.run")
    dataset_id = Column(String(36), nullable=False, index=True, comment="数据集ID")
    dashboard_id = Column(String(36), comment="生成的看板ID")
    user_id = Column(String(50), comment="执行用户")
    
    # 五阶段trace
    stage = Column(String(20), nullable=False, comment="阶段: S1/S2/S3/S4/S5")
    stage_name = Column(String(50), comment="阶段名称: 主题识别/目标生成/图表推荐/编排/评分")
    stage_status = Column(String(20), default="running", comment="状态: running/success/failed")
    stage_input = Column(JSON, comment="阶段输入")
    stage_output = Column(JSON, comment="阶段输出")
    stage_metrics = Column(JSON, comment="阶段指标，如耗时/token使用量")
    error_info = Column(JSON, comment="错误信息")
    
    # 时间戳
    started_at = Column(DateTime, default=func.now(), comment="阶段开始时间")
    completed_at = Column(DateTime, comment="阶段完成时间")
    created_at = Column(DateTime, default=func.now(), comment="记录创建时间")
    
    # 索引
    __table_args__ = (
        Index('idx_run_stage', 'run_id', 'stage'),
        Index('idx_dataset_run', 'dataset_id', 'run_id'),
    )
    
    def to_dict(self):
        return {
            "id": self.id,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "dashboard_id": self.dashboard_id,
            "user_id": self.user_id,
            "stage": self.stage,
            "stage_name": self.stage_name,
            "stage_status": self.stage_status,
            "stage_input": self.stage_input,
            "stage_output": self.stage_output,
            "stage_metrics": self.stage_metrics,
            "error_info": self.error_info,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class BrainTraceSummary(Base):
    """策略大脑执行trace汇总表 - 快速查询"""
    __tablename__ = "brain_trace_summaries"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), unique=True, nullable=False, comment="运行ID")
    dataset_id = Column(String(36), nullable=False, index=True)
    dashboard_id = Column(String(36))
    user_id = Column(String(50))
    
    # 整体状态
    overall_status = Column(String(20), default="running", comment="整体状态")
    current_stage = Column(String(20), comment="当前阶段")
    
    # 各阶段状态
    s1_status = Column(String(20), comment="S1主题识别状态")
    s2_status = Column(String(20), comment="S2目标生成状态")
    s3_status = Column(String(20), comment="S3图表推荐状态")
    s4_status = Column(String(20), comment="S4编排状态")
    s5_status = Column(String(20), comment="S5评分状态")
    
    # 最终评分
    final_score = Column(Integer, comment="最终评分")
    passed = Column(Integer, comment="是否通过: 1=通过, 0=未通过")
    
    # 时间
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    
    def to_dict(self):
        return {
            "id": self.id,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "dashboard_id": self.dashboard_id,
            "overall_status": self.overall_status,
            "current_stage": self.current_stage,
            "stages": {
                "S1": self.s1_status,
                "S2": self.s2_status,
                "S3": self.s3_status,
                "S4": self.s4_status,
                "S5": self.s5_status
            },
            "final_score": self.final_score,
            "passed": self.passed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }