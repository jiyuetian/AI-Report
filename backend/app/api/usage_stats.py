"""AI 使用统计 API（J-8）— 路由前缀 /usage-stats，由 main.py 以 /api/v1 挂载。

所有端点在进程内存中聚合（USAGE_STATS 单例），**零 DB 接触（红线④）**。
鉴权沿用 get_current_user（与 metrics.py 一致）；写入类端点同样要求登录。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.usage_stats import USAGE_STATS

router = APIRouter(prefix="/usage-stats", tags=["UsageStats"])


class RecordEventReq(BaseModel):
    event_type: str
    data: Optional[Dict[str, Any]] = None
    success: Optional[bool] = None
    latency_ms: Optional[int] = None


@router.get("/overview")
async def overview(
    time_range: str = Query("all", description="all|1h|24h|7d|30d"),
    event_type: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """总览：事件量 / 成功率 / token 消耗 / 按模型 / 按动作 / 趋势。"""
    filters = {"event_type": event_type} if event_type else None
    return USAGE_STATS.get_stats(time_range=time_range, filters=filters)


@router.get("/events")
async def events(
    limit: int = Query(50, ge=1, le=500),
    event_type: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """最近事件流（脱敏 user，供审计/调试）。"""
    return USAGE_STATS.recent_events(limit=limit, event_type=event_type)


@router.get("/trends")
async def trends(
    time_range: str = Query("24h", description="all|1h|24h|7d|30d"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """时间趋势（按小时分桶）。"""
    stats = USAGE_STATS.get_stats(time_range=time_range)
    return {"range": time_range, "trends": stats["trends"], "overview": stats["overview"]}


@router.get("/patterns")
async def patterns(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """使用模式：最常用动作 / 高峰时段 / 模型偏好 / 错误率 / 最慢模型 / 7日对比。"""
    return USAGE_STATS.analyze_patterns()


@router.post("/record")
async def record(
    req: RecordEventReq,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """手动/测试注入一条事件（生产数据由 chat.py / llm_gateway 钩子自动写入）。"""
    USAGE_STATS.record_event(
        req.event_type,
        current_user.get("sub") or current_user.get("user_id") or "manual",
        req.data,
        success=req.success,
        latency_ms=req.latency_ms,
    )
    return {"ok": True, "total": len(USAGE_STATS._events)}
