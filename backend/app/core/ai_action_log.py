"""AI 行为白盒化埋点：把每次 AI 对话动作写入 ai_action_log（SQLite 同库 aibi.db）。

设计原则（D-018 / night14 Task1）：
- fail-fast：写入失败只打印告警，**绝不向外抛异常、绝不阻断对话主流程**。
- 并发/锁安全：给写入连接设置 PRAGMA busy_timeout，遇到 SQLite 写锁时短暂等待而非长时间阻塞；
  若最终仍拿不到锁（极端并发），放弃本次日志（告警），不影响对话。
- 超大 params / error 截断：params_summary 序列化后超长截断为合法 JSON；error_msg 截断到上限。
- 调用方（chat.py）应以 `asyncio.create_task(log_ai_action(...))` 方式 fire-and-forget 调用，
  零延迟注入对话链路；本协程内部对所有异常兜底。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text

from app.models.ai_action_log import AiActionLog

_PARAMS_LIMIT = 4000   # params_summary 序列化后最大字符数
_ERROR_LIMIT = 2000    # error_msg 最大字符数
_BUSY_TIMEOUT_MS = 3000  # 写入连接等待写锁的毫秒数


def _truncate(text: Optional[str], limit: int) -> Optional[str]:
    if text is None:
        return None
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(truncated,{len(text)}->{limit})"


def _safe_params(params: Any) -> Optional[dict]:
    """把任意参数对象规整为可 JSON 序列化的摘要（超长截断且保证合法 JSON）。"""
    if params is None:
        return None
    try:
        if isinstance(params, (dict, list)):
            s = json.dumps(params, ensure_ascii=False, default=str)
        else:
            s = json.dumps({"value": params}, ensure_ascii=False, default=str)
    except Exception:
        s = json.dumps({"value": str(params)}, ensure_ascii=False)
    if len(s) > _PARAMS_LIMIT:
        s = s[:_PARAMS_LIMIT]
        try:
            json.loads(s)
        except Exception:
            s = json.dumps({"truncated": True, "note": "params too large"}, ensure_ascii=False)
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s[:_PARAMS_LIMIT]}


async def log_ai_action(
    *,
    session_id: Optional[str] = None,
    dashboard_id: Optional[str] = None,
    user_id: Optional[str] = None,
    intent: Optional[str] = None,
    action_type: Optional[str] = None,
    params_summary: Any = None,
    result_status: Optional[str] = None,
    error_msg: Optional[str] = None,
    llm_layer: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    """异步写入一条 AI 动作日志。任何异常都被吞掉并以告警形式打印，不向外抛出。

    调用方应 fire-and-forget（asyncio.create_task），不 await，以零延迟注入对话。
    """
    try:
        from app.core.database import async_session_factory

        row = AiActionLog(
            session_id=session_id,
            dashboard_id=dashboard_id,
            user_id=user_id,
            intent=intent,
            action_type=action_type,
            params_summary=_safe_params(params_summary),
            result_status=result_status,
            error_msg=_truncate(error_msg, _ERROR_LIMIT),
            llm_layer=llm_layer,
            latency_ms=latency_ms,
        )
        async with async_session_factory() as s:
            # 并发写保护：设置 busy_timeout，避免与活后端争锁时长时间阻塞对话
            try:
                await s.execute(text(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}"))
            except Exception:
                pass
            s.add(row)
            await s.commit()
    except Exception as e:
        # fail-fast：日志写失败只告警，不阻断对话
        print(f"[AI-ACTION-LOG-WARN] 写入失败(不阻断对话): {type(e).__name__}: {str(e)[:300]}")
