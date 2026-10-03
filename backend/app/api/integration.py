"""全链路联调 API（Task K）— 路由前缀 /integration，由 main.py 以 /api/v1 挂载。

POST /run   ：运行离线集成用例 + 性能基准，返回完整报告。
GET  /report：返回最近一次报告（未运行则提示先 POST）。
零 DB（红线④）；鉴权沿用 get_current_user。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.integration.test_runner import RUNNER
from app.integration.performance import run_performance_benchmark

router = APIRouter(prefix="/integration", tags=["Integration"])


@router.post("/run")
async def run(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    report = RUNNER.run_tests()
    report["performance"] = run_performance_benchmark()
    return report


@router.get("/report")
async def report(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    last = RUNNER.get_report()
    if not last:
        return {"note": "尚未运行，请先 POST /api/v1/integration/run"}
    return last
