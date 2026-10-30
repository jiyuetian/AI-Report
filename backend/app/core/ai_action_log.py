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
from typing import Any, Dict, List, Optional

from sqlalchemy import text, select

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
    run_id: Optional[str] = None,
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
            run_id=run_id,
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


async def log_contract_reasons(
    *,
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    dashboard_id: Optional[str] = None,
    reasons: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """把 S3 AI 主执行契约 reasons 逐条写入 ai_action_log（O10-2 三级留痕）。

    每条 reason 落一条 action_type='s3_contract' 的日志，run_id 关联，
    供「按 run_id 查三级留痕（阶段→契约校验→用户决策）」。任何异常被吞掉，
    不阻断 brain.run 主流程。
    """
    if not reasons:
        return
    try:
        from app.core.database import async_session_factory
        rows = []
        for r in reasons:
            if not isinstance(r, dict):
                continue
            decision = r.get("decision")
            rows.append(AiActionLog(
                run_id=run_id,
                dashboard_id=dashboard_id,
                user_id=user_id,
                intent="s3_ai_contract",
                action_type="s3_contract",
                params_summary=_safe_params(r),
                result_status="repaired" if decision in ("自修", "修复", "拦截并自修") else "passed",
                llm_layer="rule_guardrail",
            ))
        if not rows:
            return
        async with async_session_factory() as s:
            try:
                await s.execute(text(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}"))
            except Exception:
                pass
            s.add_all(rows)
            await s.commit()
    except Exception as e:
        print(f"[AI-ACTION-LOG-WARN] 契约原因写入失败(不阻断主流程): {type(e).__name__}: {str(e)[:300]}")


async def get_actions_by_run(db: AsyncSession, run_id: str) -> List[Dict[str, Any]]:
    """按 run_id 查询所有 ai_action_log（三级留痕：阶段决策/契约校验/用户决策）。"""
    result = await db.execute(
        select(AiActionLog).where(AiActionLog.run_id == run_id).order_by(AiActionLog.created_at)
    )
    rows = result.scalars().all()
    return [r.to_dict() for r in rows]
