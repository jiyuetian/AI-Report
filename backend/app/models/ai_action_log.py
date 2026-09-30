"""AI 行为日志表 —— 对话链路白盒化埋点（落在 SQLite 元数据库 aibi.db）。

字段说明：
- id / created_at / updated_at：继承自 Base（UUID 主键 + 时间戳）。
- session_id / dashboard_id / user_id：归属与维度检索。
- intent：意图分类（如 add_chart / change_chart / delete_chart / unknown）。
- action_type：具体动作类型（action / clarify / fallback / confirm_exec / remove / undo 等）。
- params_summary：动作参数摘要（JSON，写入时超长截断）。
- result_status：success / failed / rejected。
- error_msg：失败/拒绝原因（超长截断）。
- llm_layer：命中第几层模型（rule / llm / llm_add_chart 等，取自 classify_intent 的 classified_by）。
- latency_ms：本动作/本轮耗时（毫秒）。
"""
from sqlalchemy import Column, String, Integer, JSON, Text
from app.models.base import Base


class AiActionLog(Base):
    __tablename__ = "ai_action_log"

    session_id = Column(String(64), nullable=True, index=True, comment="会话ID")
    dashboard_id = Column(String(64), nullable=True, index=True, comment="看板ID")
    user_id = Column(String(64), nullable=True, index=True, comment="用户ID")
    intent = Column(String(64), nullable=True, index=True, comment="意图分类")
    action_type = Column(String(32), nullable=True, index=True, comment="动作类型")
    params_summary = Column(JSON, nullable=True, comment="参数摘要(JSON)")
    result_status = Column(String(16), nullable=True, index=True, comment="success/failed/rejected")
    error_msg = Column(Text, nullable=True, comment="失败/拒绝原因")
    llm_layer = Column(String(32), nullable=True, comment="命中第几层模型")
    latency_ms = Column(Integer, nullable=True, comment="耗时毫秒")
