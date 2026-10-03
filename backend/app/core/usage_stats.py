"""AI 使用统计（J-8）— 内存态、零 DB（红线④）。

设计约束：
- 所有事件仅存于进程内存（deque 上限 20000），**绝不接触生产 DuckDB / 任何持久化库**。
- user_id 一律脱敏：SHA-256(进程级盐 + uid) 截断，盐随机生成、不持久化（重启即变，满足隐私要求）。
- 写入失败（理论上不会，纯内存）不应影响主业务；调用方自行 try/except 兜底。

事件类型约定：
- "ai_action"   ：AI 在对话动作轮执行 CRUD/计算等动作（chat.py 钩子写入）。data 含 action_type。
- "model_call"  ：LLM 网关真实模型调用（llm_gateway 钩子写入）。data 含 model / prompt_tokens / completion_tokens。
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.analytics import (
    bucket_events,
    compute_linear_slope,
    compare_two_periods,
)

# 进程级盐：随机生成、不落盘。重启即变，保证历史不可跨进程关联（隐私设计）。
_SALT = os.urandom(8).hex()


class UsageStats:
    """进程内使用统计单例。线程安全（RLock）。"""

    def __init__(self, max_events: int = 20000):
        self._lock = threading.RLock()
        self._events: deque = deque(maxlen=max_events)

    # ---- 隐私脱敏 -------------------------------------------------------
    @staticmethod
    def _anon(uid: Any) -> str:
        if not uid:
            return "anonymous"
        try:
            s = str(uid)
        except Exception:
            s = "anonymous"
        return "u_" + hashlib.sha256((_SALT + ":" + s).encode("utf-8")).hexdigest()[:12]

    # ---- 写入 -----------------------------------------------------------
    def record_event(
        self,
        event_type: str,
        user_id: Any,
        data: Optional[Dict[str, Any]] = None,
        *,
        success: Optional[bool] = None,
        latency_ms: Optional[int] = None,
    ) -> None:
        """记录一条使用事件。

        event_type: "ai_action" | "model_call" | 其他自定义。
        user_id:     任意用户标识（会被脱敏存储）。
        data:        附加字典（动作类型 / 模型名 / token 数等）。
        success:     可选，是否成功。
        latency_ms:  可选，耗时（毫秒）。
        """
        ev: Dict[str, Any] = {
            "ts": time.time(),
            "event_type": event_type,
            "user": self._anon(user_id),
        }
        if data:
            ev["data"] = data
        if success is not None:
            ev["success"] = bool(success)
        if latency_ms is not None:
            ev["latency_ms"] = int(latency_ms)
        with self._lock:
            self._events.append(ev)

    # ---- 过滤 -----------------------------------------------------------
    def _filter(self, time_range: str = "all", filters: Optional[Dict[str, Any]] = None):
        now = time.time()
        cutoff = now
        if time_range == "1h":
            cutoff = now - 3600
        elif time_range == "24h":
            cutoff = now - 86400
        elif time_range == "7d":
            cutoff = now - 7 * 86400
        elif time_range == "30d":
            cutoff = now - 30 * 86400
        f = filters or {}
        want_type = f.get("event_type")
        want_model = f.get("model")
        with self._lock:
            evs = list(self._events)
        out = []
        for e in evs:
            if time_range not in ("all",) and e["ts"] < cutoff:
                continue
            if want_type and e["event_type"] != want_type:
                continue
            if want_model and e.get("data", {}).get("model") != want_model:
                continue
            out.append(e)
        return out

    # ---- 概览 + 按模型 / 按动作 ---------------------------------------
    def get_stats(self, time_range: str = "all", filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        events = self._filter(time_range, filters)
        total = len(events)
        succ = sum(1 for e in events if e.get("success") is True)
        err = sum(1 for e in events if e.get("success") is False)
        lat = [e["latency_ms"] for e in events if e.get("latency_ms") is not None]
        ptok = sum(e.get("data", {}).get("prompt_tokens", 0) or 0 for e in events)
        ctok = sum(e.get("data", {}).get("completion_tokens", 0) or 0 for e in events)

        type_counts: Dict[str, int] = {}
        for e in events:
            type_counts[e["event_type"]] = type_counts.get(e["event_type"], 0) + 1

        # 按模型聚合（仅 model_call 事件含 model）
        by_model: Dict[str, Dict[str, Any]] = {}
        for e in events:
            if e["event_type"] != "model_call":
                continue
            m = e.get("data", {}).get("model", "unknown")
            d = by_model.setdefault(m, {
                "model": m, "calls": 0, "success": 0, "error": 0,
                "prompt_tokens": 0, "completion_tokens": 0,
                "total_tokens": 0, "lat_sum": 0, "lat_n": 0,
            })
            d["calls"] += 1
            if e.get("success") is True:
                d["success"] += 1
            elif e.get("success") is False:
                d["error"] += 1
            d["prompt_tokens"] += e.get("data", {}).get("prompt_tokens", 0) or 0
            d["completion_tokens"] += e.get("data", {}).get("completion_tokens", 0) or 0
            d["total_tokens"] = d["prompt_tokens"] + d["completion_tokens"]
            if e.get("latency_ms") is not None:
                d["lat_sum"] += e["latency_ms"]
                d["lat_n"] += 1

        by_model_list = []
        for m, d in by_model.items():
            by_model_list.append({
                "model": d["model"],
                "calls": d["calls"],
                "success": d["success"],
                "error": d["error"],
                "success_rate": round(d["success"] / d["calls"], 4) if d["calls"] else 0.0,
                "prompt_tokens": d["prompt_tokens"],
                "completion_tokens": d["completion_tokens"],
                "total_tokens": d["total_tokens"],
                "avg_latency_ms": round(d["lat_sum"] / d["lat_n"]) if d["lat_n"] else 0,
            })
        by_model_list.sort(key=lambda x: x["calls"], reverse=True)

        # 按动作聚合（仅 ai_action 事件含 action_type）
        by_action: Dict[str, Dict[str, Any]] = {}
        for e in events:
            if e["event_type"] != "ai_action":
                continue
            a = e.get("data", {}).get("action_type", "unknown")
            d = by_action.setdefault(a, {
                "action_type": a, "count": 0, "success": 0, "error": 0,
                "lat_sum": 0, "lat_n": 0,
            })
            d["count"] += 1
            if e.get("success") is True:
                d["success"] += 1
            elif e.get("success") is False:
                d["error"] += 1
            if e.get("latency_ms") is not None:
                d["lat_sum"] += e["latency_ms"]
                d["lat_n"] += 1
        by_action_list = []
        for a, d in by_action.items():
            by_action_list.append({
                "action_type": d["action_type"],
                "count": d["count"],
                "success": d["success"],
                "error": d["error"],
                "success_rate": round(d["success"] / d["count"], 4) if d["count"] else 0.0,
                "avg_latency_ms": round(d["lat_sum"] / d["lat_n"]) if d["lat_n"] else 0,
            })
        by_action_list.sort(key=lambda x: x["count"], reverse=True)

        # 时间趋势（按小时分桶，最近 24 桶；不足则按数据范围）
        trends = bucket_events(events, unit="hour", buckets=24)

        return {
            "range": time_range,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overview": {
                "total_events": total,
                "success": succ,
                "error": err,
                "success_rate": round(succ / total, 4) if total else 0.0,
                "event_types": type_counts,
                "total_prompt_tokens": ptok,
                "total_completion_tokens": ctok,
                "total_tokens": ptok + ctok,
                "avg_latency_ms": round(sum(lat) / len(lat)) if lat else 0,
            },
            "by_model": by_model_list,
            "by_action": by_action_list,
            "trends": trends,
        }

    # ---- 使用模式分析 ---------------------------------------------------
    def analyze_patterns(self) -> Dict[str, Any]:
        events = self._filter("all")
        # 最常用动作
        act_counter: Dict[str, int] = {}
        for e in events:
            if e["event_type"] == "ai_action":
                a = e.get("data", {}).get("action_type", "unknown")
                act_counter[a] = act_counter.get(a, 0) + 1
        top_actions = sorted(act_counter.items(), key=lambda kv: kv[1], reverse=True)[:10]

        # 高峰时段（按 UTC 小时）
        hour_counter = [0] * 24
        for e in events:
            hour_counter[datetime.fromtimestamp(e["ts"], tz=timezone.utc).hour] += 1
        peak_hour = int(max(range(24), key=lambda h: hour_counter[h])) if any(hour_counter) else -1

        # 模型偏好占比 + 各模型错误率
        model_calls: Dict[str, int] = {}
        model_err: Dict[str, int] = {}
        for e in events:
            if e["event_type"] != "model_call":
                continue
            m = e.get("data", {}).get("model", "unknown")
            model_calls[m] = model_calls.get(m, 0) + 1
            if e.get("success") is False:
                model_err[m] = model_err.get(m, 0) + 1
        total_calls = sum(model_calls.values()) or 1
        model_preference = {m: round(c / total_calls, 4) for m, c in model_calls.items()}
        error_rate_by_model = {
            m: round(model_err.get(m, 0) / c, 4) for m, c in model_calls.items()
        }

        # 最慢模型（平均延迟）
        lat_sum: Dict[str, int] = {}
        lat_n: Dict[str, int] = {}
        for e in events:
            if e["event_type"] == "model_call" and e.get("latency_ms") is not None:
                m = e.get("data", {}).get("model", "unknown")
                lat_sum[m] = lat_sum.get(m, 0) + e["latency_ms"]
                lat_n[m] = lat_n.get(m, 0) + 1
        slowest = sorted(
            ((m, round(lat_sum[m] / lat_n[m])) for m in lat_sum),
            key=lambda kv: kv[1], reverse=True
        )[:5]

        return {
            "top_actions": [{"action_type": a, "count": c} for a, c in top_actions],
            "peak_hour_utc": peak_hour,
            "model_preference": model_preference,
            "error_rate_by_model": error_rate_by_model,
            "slowest_models": [{"model": m, "avg_latency_ms": v} for m, v in slowest],
            "compare_7d": compare_two_periods(events, days=7),
        }

    # ---- 最近事件（审计/调试视图） -------------------------------------
    def recent_events(self, limit: int = 50, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            evs = list(self._events)
        if event_type:
            evs = [e for e in evs if e["event_type"] == event_type]
        evs = evs[-limit:]
        out = []
        for e in evs:
            item = {
                "ts": datetime.fromtimestamp(e["ts"], tz=timezone.utc).isoformat(),
                "event_type": e["event_type"],
                "user": e.get("user"),
            }
            if "success" in e:
                item["success"] = e["success"]
            if "latency_ms" in e:
                item["latency_ms"] = e["latency_ms"]
            if "data" in e:
                item["data"] = e["data"]
            out.append(item)
        return out


# 全局单例（被 chat.py / llm_gateway 钩子共享）
USAGE_STATS = UsageStats()
