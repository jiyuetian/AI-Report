"""全链路联调运行器（Task K）。

离线运行所有用例（红线④：零 DB），产出结构化报告。
报告可被前端 E2ETestPage 拉取展示通过率与逐条结果。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from app.integration.test_cases import CASES


class IntegrationTestRunner:
    def __init__(self) -> None:
        self._last_report: Dict[str, Any] = {}

    def run_tests(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        for c in CASES:
            t0 = time.time()
            try:
                raw = c["run"]()  # type: ignore[operator]
                # 兼容两种契约：IntegrationTestCase.run() 只返回 bool；
                # 若用例自行返回 (bool, str) 元组则直接用。
                if isinstance(raw, tuple) and len(raw) == 2:
                    ok, detail = raw
                elif isinstance(raw, bool):
                    ok, detail = raw, ""
                else:
                    ok, detail = False, f"unexpected return: {type(raw).__name__}"
            except Exception as e:  # 异常即失败（诚实，不伪造 PASS）
                ok, detail = False, f"{type(e).__name__}: {e}"
            results.append({
                "id": c["id"],
                "name": c["name"],
                "group": c["group"],
                "passed": bool(ok),
                "detail": str(detail),
                "latency_ms": int((time.time() - t0) * 1000),
            })
        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        self._last_report = {
            "generated_at": time.time(),
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "mode": "offline-smoke(零DB)",
            "results": results,
        }
        return self._last_report

    def get_report(self) -> Dict[str, Any]:
        return self._last_report or self.run_tests()


# 模块级单例（被 integration API 复用）
RUNNER = IntegrationTestRunner()
