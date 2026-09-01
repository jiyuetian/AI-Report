"""
对话模型 - M3-01
"""
from sqlalchemy import Column, String, DateTime, JSON, Text, Integer, ForeignKey, Index
from sqlalchemy.sql import func
from app.models.base import Base
import uuid
from enum import Enum


class IntentType(str, Enum):
    """意图类型"""
    CHANGE_CHART = "change_chart"      # 换图
    ADD_CHART = "add_chart"            # 新增图
    FILTER_DRILL = "filter_drill"      # 筛选下钻
    ATTRIBUTION = "attribution"        # 归因追问
    EDIT_TITLE = "edit_title"          # 标题编辑
    UNKNOWN = "unknown"                # 未知


class ChatSession(Base):
    """对话会话表"""
    __tablename__ = "chat_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False, index=True)
    dashboard_id = Column(String(36), ForeignKey("dashboards.id"), nullable=True)
    dataset_id = Column(String(36), nullable=True)
    
    # 上下文
    context = Column(JSON, default={}, comment="上下文：字段画像+看板配置")
    
    # 状态
    status = Column(String(20), default="active", comment="active/closed")
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "dashboard_id": self.dashboard_id,
            "dataset_id": self.dataset_id,
            "context": self.context,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class ChatMessage(Base):
    """对话消息表 - 用户行为标注"""
    __tablename__ = "chat_messages"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    
    # 消息内容
    role = Column(String(20), nullable=False, comment="user/assistant/system")
    content = Column(Text, nullable=False)
    
    # 意图识别 (M3-01)
    intent_type = Column(String(50), comment="意图类型")
    intent_confidence = Column(Integer, comment="意图置信度 0-100")
    intent_analysis = Column(JSON, comment="意图分析详情")
    
    # 动作执行 (M3-02)
    action_type = Column(String(50), comment="动作类型")
    action_params = Column(JSON, comment="动作参数")
    action_result = Column(JSON, comment="动作执行结果")
    
    # Token计量 (M3-03)
    tokens_used = Column(Integer, default=0)
    
    # 审核信息 (M3-04)
    moderation_status = Column(String(20), default="passed", comment="passed/blocked")
    moderation_reason = Column(String(200))
    
    # 重试机制
    retry_count = Column(Integer, default=0)
    original_content = Column(Text, comment="发送失败时保留的原文")
    
    created_at = Column(DateTime, default=func.now())
    
    # 索引
    __table_args__ = (
        Index('idx_chat_session_time', 'session_id', 'created_at'),
        Index('idx_chat_intent', 'intent_type'),
    )
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "intent_type": self.intent_type,
            "intent_confidence": self.intent_confidence,
            "intent_analysis": self.intent_analysis,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "action_result": self.action_result,
            "tokens_used": self.tokens_used,
            "moderation_status": self.moderation_status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class TokenQuota(Base):
    """Token配额表 - M3-03"""
    __tablename__ = "token_quotas"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False, unique=True, index=True)
    
    # 配额
    daily_limit = Column(Integer, default=5000, comment="每日上限")
    used_today = Column(Integer, default=0, comment="今日已用")
    remaining = Column(Integer, default=5000, comment="剩余")
    
    # 预警
    warning_threshold = Column(Integer, default=90, comment="预警阈值%")
    is_warning_shown = Column(Integer, default=0, comment="今日预警已显示")
    is_exhausted = Column(Integer, default=0, comment="是否已耗尽")
    
    # 重置时间
    last_reset_at = Column(DateTime, default=func.now())
    
    # 加量申请 (M3-06)
    extra_quota = Column(Integer, default=0, comment="临时加量")
    extra_expires_at = Column(DateTime, comment="加量过期时间")
    
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "daily_limit": self.daily_limit,
            "used_today": self.used_today,
            "remaining": self.remaining,
            "extra_quota": self.extra_quota,
            "usage_percent": round((self.used_today / self.daily_limit) * 100, 1) if self.daily_limit > 0 else 0
        }


class TokenApplication(Base):
    """Token加量申请表 - M3-06"""
    __tablename__ = "token_applications"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False, index=True)
    
    # 申请信息
    apply_amount = Column(Integer, nullable=False, comment="申请数量")
    apply_reason = Column(Text, comment="申请理由")
    status = Column(String(20), default="pending", comment="pending/approved/rejected")
    
    # 审批信息
    approved_by = Column(String(50))
    approved_amount = Column(Integer)
    approve_comment = Column(Text)
    
    # 有效期
    expires_at = Column(DateTime)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "apply_amount": self.apply_amount,
            "apply_reason": self.apply_reason,
            "status": self.status,
            "approved_by": self.approved_by,
            "approved_amount": self.approved_amount,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }