"""AI 行为日志查询 API（D-018 / night14 Task2）。

把 chat 链路埋进 ai_action_log 的「写」动作，在这里提供「读」能力：分页 + 多维过滤 + 权限隔离。
设计要点：
- 普通用户：强制只看自己（user_id == 当前登录用户）的日志，不接受客户端伪造的 user_id。
- 超管：可看全部；若显式传 user_id 则按该 user_id 过滤（可检索 legacy/anonymous 数据）。
- 过滤维度：session_id / dashboard_id / action_type / intent / result_status / llm_layer /
  时间区间(start_time/end_time, ISO-8601) / keyword(模糊匹配 error_msg+action_type+intent)。
- 仅查询，不写 ai_action_log，不触碰业务 DuckDB；fail-safe：任何异常都转成 500 明细而非吞掉。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ai_action_log import AiActionLog

router = APIRouter(prefix="/ai-action-log", tags=["AiActionLog"])


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------
class AiActionLogItem(BaseModel):
    id: str
    session_id: Optional[str] = None
    dashboard_id: Optional[str] = None
    user_id: Optional[str] = None
    intent: Optional[str] = None
    action_type: Optional[str] = None
    params_summary: Optional[dict] = None
    result_status: Optional[str] = None
    error_msg: Optional[str] = None
    llm_layer: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: Optional[str] = None  # ISO-8601 字符串


class AiActionLogListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: List[AiActionLogItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """把 ISO-8601 字符串解析为「无时区(UTC naive)」datetime，便于与 SQLite 存储的 naive 时间比较。"""
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except Exception:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _item_from_row(row: AiActionLog) -> AiActionLogItem:
    ca = row.created_at
    if isinstance(ca, datetime):
        ca = ca.isoformat()
    return AiActionLogItem(
        id=row.id,
        session_id=row.session_id,
        dashboard_id=row.dashboard_id,
        user_id=row.user_id,
        intent=row.intent,
        action_type=row.action_type,
        params_summary=row.params_summary,
        result_status=row.result_status,
        error_msg=row.error_msg,
        llm_layer=row.llm_layer,
        latency_ms=row.latency_ms,
        created_at=ca,
    )


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------
@router.get("/list", response_model=AiActionLogListResponse)
async def list_ai_action_logs(
    session_id: Optional[str] = Query(None, description="会话ID精确过滤"),
    dashboard_id: Optional[str] = Query(None, description="看板ID精确过滤"),
    action_type: Optional[str] = Query(None, description="动作类型(add_chart/delete_chart/undo/...)"),
    intent: Optional[str] = Query(None, description="意图分类"),
    result_status: Optional[str] = Query(None, description="结果: success/failed"),
    llm_layer: Optional[str] = Query(None, description="命中模型层(rule/llm/confirmation_word/...)"),
    user_id: Optional[str] = Query(None, description="仅超管可用：按用户过滤(默认查全部)"),
    start_time: Optional[str] = Query(None, description="起始时间 ISO-8601(含)"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO-8601(含)"),
    keyword: Optional[str] = Query(None, description="模糊匹配 error_msg/action_type/intent"),
    page: int = Query(1, ge=1, description="页码(从1开始)"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """分页 + 多维过滤查询 AI 行为日志。权限隔离见模块说明。"""
    is_super = bool(current_user.get("is_superuser"))
    caller_uid = current_user.get("user_id")

    # 权限隔离：普通用户只能看自己；超管可看全部或按 user_id 过滤
    eff_user: Optional[str] = None
    if not is_super:
        eff_user = caller_uid
    else:
        eff_user = user_id if user_id else None

    # 组装过滤条件
    filters = []
    if eff_user is not None:
        filters.append(AiActionLog.user_id == eff_user)
    if session_id:
        filters.append(AiActionLog.session_id == session_id)
    if dashboard_id:
        filters.append(AiActionLog.dashboard_id == dashboard_id)
    if action_type:
        filters.append(AiActionLog.action_type == action_type)
    if intent:
        filters.append(AiActionLog.intent == intent)
    if result_status:
        filters.append(AiActionLog.result_status == result_status)
    if llm_layer:
        filters.append(AiActionLog.llm_layer == llm_layer)
    if keyword:
        kw = f"%{keyword}%"
        filters.append(
            or_(
                AiActionLog.error_msg.like(kw),
                AiActionLog.action_type.like(kw),
                AiActionLog.intent.like(kw),
            )
        )
    start_dt = _parse_dt(start_time)
    if start_dt is not None:
        filters.append(AiActionLog.created_at >= start_dt)
    end_dt = _parse_dt(end_time)
    if end_dt is not None:
        filters.append(AiActionLog.created_at <= end_dt)

    where = and_(*filters) if filters else True

    # 总数
    total_res = await db.execute(
        select(func.count()).select_from(AiActionLog).where(where)
    )
    total = int(total_res.scalar() or 0)

    # 分页取数（按时间倒序）
    offset = (page - 1) * page_size
    rows_res = await db.execute(
        select(AiActionLog)
        .where(where)
        .order_by(AiActionLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = rows_res.scalars().all()
    items = [_item_from_row(r) for r in rows]

    return AiActionLogListResponse(total=total, page=page, page_size=page_size, items=items)
