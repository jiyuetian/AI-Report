"""性能基准（Task K）— 离线测量关键引擎吞吐延迟。

测两个热路径：派生指标 calculate 往返、使用统计 record+get_stats 往返。
输出 p50/p95/max/mean（毫秒）。零 DB、零网络。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List


def _pct(xs: List[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(p / 100 * len(s))))
    return round(s[k], 3)


def run_performance_benchmark(iterations: int = 300) -> Dict[str, Any]:
    from app.core.metric_registry import METRIC_REGISTRY
    from app.core.usage_stats import USAGE_STATS

    metric_lats: List[float] = []
    ms = METRIC_REGISTRY.list_metrics()
    name = ms[0] if ms else "roi"
    for _ in range(iterations):
        t0 = time.time()
        try:
            METRIC_REGISTRY.calculate(name, {}, operation="query")
        except Exception:
            pass
        metric_lats.append((time.time() - t0) * 1000)

    usage_lats: List[float] = []
    for i in range(iterations):
        t0 = time.time()
        USAGE_STATS.record_event("perf_probe", f"bench{i}",
                                  {"model": "bench"}, success=True, latency_ms=1)
        USAGE_STATS.get_stats("all")
        usage_lats.append((time.time() - t0) * 1000)

    def _summ(xs: List[float]) -> Dict[str, float]:
        return {
            "p50": _pct(xs, 50),
            "p95": _pct(xs, 95),
            "max": round(max(xs), 3),
            "mean": round(sum(xs) / len(xs), 3),
        }

    return {
        "iterations": iterations,
        "metric_calc_ms": _summ(metric_lats),
        "usage_roundtrip_ms": _summ(usage_lats),
    }
