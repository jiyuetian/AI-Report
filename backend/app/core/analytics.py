"""使用统计的分析引擎（J-8 配套）— 纯函数、无状态、零 DB。

被 usage_stats.py 的 UsageStats 调用，也可独立单测。
所有函数输入/输出均为可 JSON 序列化的原生类型。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def compute_linear_slope(xs: List[float], ys: List[float]) -> float:
    """最小二乘斜率。样本不足返回 0.0（诚实不编造）。"""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def bucket_events(
    events: List[Dict[str, Any]],
    unit: str = "hour",
    buckets: int = 24,
) -> List[Dict[str, Any]]:
    """把事件按时间分桶，输出稳定时间轴的趋势序列。

    unit: "hour" | "day"。桶从「当前时刻往前 buckets 个」开始，保证 x 轴稳定。
    返回: [{bucket, ts, total, success, error}, ...]
    """
    step = 3600 if unit == "hour" else 86400
    now = max((e["ts"] for e in events), default=0.0)
    if now == 0.0:
        now = __import__("time").time()
    now_bucket = int(now // step)
    grid = [now_bucket - (buckets - 1 - i) for i in range(buckets)]
    index: Dict[int, Dict[str, int]] = {b: {"total": 0, "success": 0, "error": 0} for b in grid}
    for e in events:
        b = int(e["ts"] // step)
        if b in index:
            slot = index[b]
            slot["total"] += 1
            if e.get("success") is True:
                slot["success"] += 1
            elif e.get("success") is False:
                slot["error"] += 1
    out: List[Dict[str, Any]] = []
    for b in grid:
        slot = index[b]
        out.append({
            "bucket": b,
            "ts": datetime.fromtimestamp(b * step, tz=timezone.utc).isoformat(),
            "total": slot["total"],
            "success": slot["success"],
            "error": slot["error"],
        })
    return out


def compare_two_periods(events: List[Dict[str, Any]], days: int = 7) -> Dict[str, Any]:
    """把全部事件按「现在往前 days 天」切分前后两段，比较使用量与成功率。"""
    import time
    now = time.time()
    split = now - days * 86400

    def _agg(sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(sub)
        succ = sum(1 for e in sub if e.get("success") is True)
        return {
            "count": total,
            "success_rate": round(succ / total, 4) if total else 0.0,
        }

    before = [e for e in events if e["ts"] < split]
    after = [e for e in events if e["ts"] >= split]
    b = _agg(before)
    a = _agg(after)
    delta = round(a["success_rate"] - b["success_rate"], 4)
    return {
        "split_days": days,
        "before": b,
        "after": a,
        "delta_success_rate": delta,
        "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


def top_n_counter(items: List[str], n: int = 10) -> List[Dict[str, Any]]:
    """计数取 Top-N，返回 [{key, count}, ...]。"""
    counter: Dict[str, int] = {}
    for it in items:
        counter[it] = counter.get(it, 0) + 1
    ranked = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"key": k, "count": c} for k, c in ranked]
