"""审计日志框架"""
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request

from app.models.audit import AuditLog


class AuditLogger:
    """审计日志记录器"""

    def __init__(self):
        self._buffer = []
        self._max_buffer_size = 100

    def _flush(self):
        """将缓冲区日志写出（同步实现，避免启动时无事件循环）"""
        if not self._buffer:
            return

        logs = self._buffer[:]
        self._buffer = []

        # TODO: 批量写入数据库（当前简化处理，仅打印）
        for log_data in logs:
            try:
                # 敏感字段加密
                encrypted_detail = self._encrypt_sensitive_data(log_data.get("detail", {}))
                print(f"[AUDIT] {log_data.get('action')} by {log_data.get('user')} from {log_data.get('ip')}")
            except Exception as e:
                print(f"[AUDIT ERROR] Failed to save audit log: {e}")

    def _encrypt_sensitive_data(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        """加密敏感数据"""
        sensitive_fields = ['password', 'token', 'secret', 'key', 'credit_card']
        encrypted = detail.copy()

        for field in sensitive_fields:
            if field in encrypted:
                # 使用SHA256哈希敏感字段
                value = str(encrypted[field])
                encrypted[field] = hashlib.sha256(value.encode()).hexdigest()[:16] + "..."

        return encrypted

    def log(self, action: str, user: Optional[str] = None,
            object_type: Optional[str] = None, object_id: Optional[str] = None,
            ip: Optional[str] = None, result: str = "success",
            detail: Optional[Dict[str, Any]] = None):
        """记录审计日志"""
        log_entry = {
            "action": action,
            "user": user,
            "object_type": object_type,
            "object_id": object_id,
            "ip": ip,
            "result": result,
            "detail": detail or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        self._buffer.append(log_entry)

        # 缓冲区满立即刷盘
        if len(self._buffer) >= self._max_buffer_size:
            self._flush()

    async def query_logs(self, user: Optional[str] = None,
                        action: Optional[str] = None,
                        start_time: Optional[datetime] = None,
                        end_time: Optional[datetime] = None,
                        limit: int = 100) -> list:
        """查询审计日志"""
        # TODO: 实现查询逻辑
        return []


# 全局审计日志实例
_audit_logger = AuditLogger()


def audit_log(action: str, user: Optional[str] = None,
              object_type: Optional[str] = None, object_id: Optional[str] = None,
              ip: Optional[str] = None, result: str = "success",
              detail: Optional[Dict[str, Any]] = None):
    """
    记录审计日志（便捷函数）

    使用示例:
        audit_log(
            action="login_success",
            user="zhangsan",
            ip=request.client.host,
            detail={"user_id": "123"}
        )
    """
    _audit_logger.log(
        action=action,
        user=user,
        object_type=object_type,
        object_id=object_id,
        ip=ip,
        result=result,
        detail=detail
    )


# 常用操作类型
class AuditActions:
    """审计操作类型常量"""

    # 认证相关
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_RESET = "password_reset"
    SEND_VERIFY_CODE = "send_verify_code"

    # 文件相关
    FILE_UPLOAD = "file_upload"
    FILE_DELETE = "file_delete"
    FILE_DOWNLOAD = "file_download"

    # 数据相关
    DATASET_CREATE = "dataset_create"
    DATASET_DELETE = "dataset_delete"
    QUALITY_FIX = "quality_fix"

    # 看板相关
    DASHBOARD_CREATE = "dashboard_create"
    DASHBOARD_UPDATE = "dashboard_update"
    DASHBOARD_DELETE = "dashboard_delete"
    DASHBOARD_SHARE = "dashboard_share"
    DASHBOARD_EXPORT = "dashboard_export"

    # 对话相关
    CHAT_MESSAGE = "chat_message"
    CHART_GENERATE = "chart_generate"

    # 管理相关
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    ROLE_ASSIGN = "role_assign"
    QUOTA_ADJUST = "quota_adjust"