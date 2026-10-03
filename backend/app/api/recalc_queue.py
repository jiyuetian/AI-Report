"""
下游重算队列 API（night15-16 Task I：C-16）

- RecalcQueue：对 RECLAC_ENGINE 的薄封装（满足指令「重算队列」类形态）。
- router：触发 / 状态 / 历史 / 依赖图 / 性能统计 / 恢复 六个端点。

全部为只读计算 + 内存队列，不碰生产 DuckDB（红线④）。
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.recalc_engine import RECLAC_ENGINE


class RecalcQueue:
    """重算队列薄封装（委托给进程内 RECLAC_ENGINE）。"""

    def __init__(self, engine=None):
        self.engine = engine or RECLAC_ENGINE

    def add_task(self, metric_names: List[str], priority: int = 0) -> Dict[str, Any]:
        return self.engine.notify_data_change({"metric_names": metric_names, "priority": priority})

    def get_status(self) -> Dict[str, Any]:
        return self.engine.get_status()

    def trigger(self, change: Dict[str, Any], data: Optional[Dict[str, Any]] = None,
                dry_run: bool = False) -> Dict[str, Any]:
        note = self.engine.notify_data_change(change)
        if dry_run or not note.get("success"):
            return note
        return self.engine.execute_recalc(recalc_id=note.get("recalc_id"), data_provider=data)


router = APIRouter()
_queue = RecalcQueue()


class TriggerBody(BaseModel):
    scope: Optional[str] = None
    metric_names: Optional[List[str]] = None
    data: Optional[Dict[str, Any]] = None     # {metric_key: {"data":{...}} 或 {"old_data":{},"new_data":{}}}
    dry_run: bool = False


class RecoverBody(BaseModel):
    recalc_id: str


@router.post("/trigger")
async def trigger(body: TriggerBody, request: Request):
    change = {"scope": body.scope, "metric_names": body.metric_names,
              "trigger_source": "api"}
    return _queue.trigger(change, data=body.data, dry_run=body.dry_run)


@router.get("/status")
async def status(recalc_id: Optional[str] = None):
    return _queue.get_status() if not recalc_id else RECLAC_ENGINE.get_status(recalc_id)


@router.get("/history")
async def history():
    return RECLAC_ENGINE.list_history()


@router.get("/dependency-graph")
async def dependency_graph():
    from app.core.dependency_graph import DependencyGraph
    return {"success": True, **DependencyGraph().to_graph_view()}


@router.get("/stats")
async def stats():
    return RECLAC_ENGINE.get_stats()


@router.post("/recover")
async def recover(body: RecoverBody):
    return RECLAC_ENGINE.recover(body.recalc_id)
