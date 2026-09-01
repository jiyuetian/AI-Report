"""
事件日志 - 用户反馈采集飞轮
记录用户操作事件，用于后续分析和模型优化
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class EventLogger:
    """事件日志器"""
    
    _instance = None
    
    def __init__(self):
        log_dir = Path(__file__).parent.parent.parent / "logs" / "events"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = log_dir / f"user_events_{datetime.now().strftime('%Y%m')}.jsonl"
    
    @classmethod
    def get_instance(cls) -> "EventLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def log_event(
        self,
        event_type: str,
        user_id: str,
        details: Dict[str, Any],
        dashboard_id: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        """记录用户事件"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "dashboard_id": dashboard_id,
            "session_id": session_id,
            "details": details
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志写入失败不阻塞主流程


# 便捷函数
def log_user_action(
    event_type: str,
    user_id: str,
    details: Dict[str, Any],
    dashboard_id: Optional[str] = None,
    session_id: Optional[str] = None
):
    """记录用户操作"""
    EventLogger.get_instance().log_event(
        event_type=event_type,
        user_id=user_id,
        details=details,
        dashboard_id=dashboard_id,
        session_id=session_id
    )