"""派生指标 API - night15-16 Task H（派生指标完整版）。

只读计算接口（不碰 DB，不碰 aibi.db，满足红线④）：
- GET  /registry    列出全部 14 个指标的元信息（名称/公式/字段/来源/单位）
- POST /calculate   按 operation 计算：query(单期) / explain(解释) / compare(多期对比) / trend(趋势预测)

数据由调用方以 dict 显式提供（字段→数值），AI 查询时由对话链路解析字段值后传入。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.metric_registry import METRIC_REGISTRY

router = APIRouter(prefix="/metrics", tags=["Metrics"])


class MetricCalculateReq(BaseModel):
    metric: str = Field(..., description="指标名（中文名/英文键/别名，由注册表解析）")
    operation: str = Field("query", description="query / explain / compare / trend")
    data: Dict[str, Any] = Field(default_factory=dict, description="字段值 dict 或 periods/history 结构")
    use_cache: bool = True


@router.get("/registry")
async def registry(current_user: Dict[str, Any] = Depends(get_current_user)):
    """列出全部派生指标元信息。"""
    return {
        "success": True,
        "count": len(METRIC_REGISTRY.list_metrics()),
        "metrics": METRIC_REGISTRY.list_metrics(),
    }


@router.post("/calculate")
async def calculate(
    req: MetricCalculateReq,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """计算指定指标（query/explain/compare/trend）。"""
    res = METRIC_REGISTRY.calculate(
        req.metric, req.data, operation=req.operation, use_cache=req.use_cache
    )
    return res
