"""
AI 使用统计（night17 Task J-8）
零 DB、内存态、进程级统计（红线④）

- UsageStats 单例 USAGE_STATS：进程内 deque 存事件（上限 20000）
- user_id 一律 SHA-256(进程级随机盐) 脱敏、盐不持久化（隐私）
- fail-safe 写入：异常只跳过不阻断主业务
"""

import time
import hashlib
import random
from typing import Dict, Any, List, Optional, Union
from collections import defaultdict, deque
from datetime import datetime, timedelta


class UsageStats:
    """AI 使用统计单例（内存态，零 DB）"""

    def __init__(self):
        # 进程级随机盐（不持久化，重启即变）
        self._salt = str(random.random()).encode()
        
        # 事件队列（最多 20000 条，FIFO）
        self._events: deque = deque(maxlen=20000)
        
        # 缓存统计结果（避免重复计算）
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, float] = {}
        
    def _hash_user_id(self, user_id: Optional[str]) -> Optional[str]:
        """user_id 脱敏：SHA-256(盐 + user_id)"""
        if not user_id:
            return None
        data = f"{self._salt.decode()}{user_id}".encode()
        return hashlib.sha256(data).hexdigest()
    
    def record_event(self, event_type: str, user_id: Optional[str] = None, 
                    data: Optional[Dict[str, Any]] = None, 
                    success: bool = True, latency_ms: Optional[float] = None):
        """记录使用事件（fail-safe，异常只跳过不阻断）"""
        try:
            event = {
                "event_type": event_type,
                "user_id": self._hash_user_id(user_id),
                "timestamp": time.time(),
                "data": data or {},
                "success": success,
                "latency_ms": latency_ms,
            }
            self._events.append(event)
            
            # 清除相关缓存
            self._cache.clear()
            self._cache_ttl.clear()
            
        except Exception:
            # 静默失败，不阻断主业务
            pass
    
    def get_stats(self, time_range: Optional[str] = "1h", 
                 filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取统计概览"""
        cache_key = f"stats_{time_range}_{hash(str(filters))}"
        
        # 缓存检查（TTL 30 秒）
        if cache_key in self._cache and time.time() - self._cache_ttl[cache_key] < 30:
            return self._cache[cache_key]
        
        # 计算时间范围
        end_time = time.time()
        if time_range == "1h":
            start_time = end_time - 3600
        elif time_range == "24h":
            start_time = end_time - 86400
        elif time_range == "7d":
            start_time = end_time - 7 * 86400
        else:  # 默认 1h
            start_time = end_time - 3600
        
        # 过滤事件
        filtered_events = []
        for event in self._events:
            if event["timestamp"] >= start_time:
                if filters:
                    match = True
                    for key, value in filters.items():
                        if key in event and event[key] != value:
                            match = False
                            break
                    if match:
                        filtered_events.append(event)
                else:
                    filtered_events.append(event)
        
        # 基础统计
        total_events = len(filtered_events)
        success_events = sum(1 for e in filtered_events if e["success"])
        success_rate = success_events / total_events if total_events > 0 else 0
        
        # 总 token 消耗
        total_tokens = 0
        for event in filtered_events:
            if event["data"].get("prompt_tokens"):
                total_tokens += event["data"]["prompt_tokens"]
            if event["data"].get("completion_tokens"):
                total_tokens += event["data"]["completion_tokens"]
        
        # 平均延迟
        valid_latencies = [e["latency_ms"] for e in filtered_events 
                          if e["latency_ms"] is not None]
        avg_latency = sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0
        
        # 按模型统计
        model_stats = defaultdict(lambda: {"count": 0, "success": 0, "tokens": 0, "latency": []})
        for event in filtered_events:
            model_name = event["data"].get("model", "unknown")
            model_stats[model_name]["count"] += 1
            if event["success"]:
                model_stats[model_name]["success"] += 1
            if event["data"].get("prompt_tokens"):
                model_stats[model_name]["tokens"] += event["data"]["prompt_tokens"]
            if event["data"].get("completion_tokens"):
                model_stats[model_name]["tokens"] += event["data"]["completion_tokens"]
            if event["latency_ms"] is not None:
                model_stats[model_name]["latency"].append(event["latency_ms"])
        
        # 计算模型详细统计
        detailed_model_stats = {}
        for model, stats in model_stats.items():
            detailed_model_stats[model] = {
                "count": stats["count"],
                "success_rate": stats["success"] / stats["count"] if stats["count"] > 0 else 0,
                "total_tokens": stats["tokens"],
                "avg_latency_ms": sum(stats["latency"]) / len(stats["latency"]) if stats["latency"] else 0,
            }
        
        # 按动作统计
        action_stats = defaultdict(lambda: {"count": 0, "success": 0})
        for event in filtered_events:
            action_type = event["event_type"]
            action_stats[action_type]["count"] += 1
            if event["success"]:
                action_stats[action_type]["success"] += 1
        
        detailed_action_stats = {}
        for action, stats in action_stats.items():
            detailed_action_stats[action] = {
                "count": stats["count"],
                "success_rate": stats["success"] / stats["count"] if stats["count"] > 0 else 0,
            }
        
        result = {
            "overview": {
                "total_events": total_events,
                "success_events": success_events,
                "success_rate": round(success_rate, 4),
                "total_tokens": total_tokens,
                "avg_latency_ms": round(avg_latency, 2),
            },
            "by_model": detailed_model_stats,
            "by_action": detailed_action_stats,
            "time_range": time_range,
            "filtered_count": len(filtered_events),
        }
        
        # 缓存结果
        self._cache[cache_key] = result
        self._cache_ttl[cache_key] = time.time()
        
        return result
    
    def analyze_patterns(self) -> Dict[str, Any]:
        """分析使用模式"""
        cache_key = "patterns"
        
        # 缓存检查（TTL 60 秒）
        if cache_key in self._cache and time.time() - self._cache_ttl[cache_key] < 60:
            return self._cache[cache_key]
        
        # 最近 7 天数据
        end_time = time.time()
        start_time = end_time - 7 * 86400
        
        recent_events = [e for e in self._events if e["timestamp"] >= start_time]
        
        # 最常用动作 Top 5
        action_counts = defaultdict(int)
        for event in recent_events:
            action_counts[event["event_type"]] += 1
        
        top_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 高峰时段分析（按小时）
        hourly_usage = defaultdict(int)
        for event in recent_events:
            hour = datetime.fromtimestamp(event["timestamp"]).hour
            hourly_usage[hour] += 1
        
        peak_hour = max(hourly_usage.items(), key=lambda x: x[1])[0]
        
        # 模型偏好
        model_preference = defaultdict(lambda: {"count": 0, "success": 0})
        for event in recent_events:
            model = event["data"].get("model", "unknown")
            model_preference[model]["count"] += 1
            if event["success"]:
                model_preference[model]["success"] += 1
        
        model_stats = {}
        for model, stats in model_preference.items():
            model_stats[model] = {
                "usage_count": stats["count"],
                "success_rate": stats["success"] / stats["count"] if stats["count"] > 0 else 0,
            }
        
        # 各模型错误率
        error_rates = {}
        for model, stats in model_stats.items():
            error_rates[model] = round(1 - stats["success_rate"], 4)
        
        # 最慢模型（按平均延迟）
        model_latencies = defaultdict(list)
        for event in recent_events:
            model = event["data"].get("model", "unknown")
            if event["latency_ms"] is not None:
                model_latencies[model].append(event["latency_ms"])
        
        slowest_model = None
        max_avg_latency = 0
        for model, latencies in model_latencies.items():
            avg_latency = sum(latencies) / len(latencies)
            if avg_latency > max_avg_latency:
                max_avg_latency = avg_latency
                slowest_model = model
        
        # 7 日前后对比（最近 1 天 vs 前 6 天）
        recent_1d = [e for e in recent_events if e["timestamp"] >= end_time - 86400]
        previous_6d = [e for e in recent_events if end_time - 7 * 86400 <= e["timestamp"] < end_time - 86400]
        
        def compute_period_stats(events):
            if not events:
                return {"total": 0, "success": 0, "tokens": 0}
            return {
                "total": len(events),
                "success": sum(1 for e in events if e["success"]),
                "tokens": sum(e["data"].get("prompt_tokens", 0) + e["data"].get("completion_tokens", 0) 
                           for e in events),
            }
        
        recent_stats = compute_period_stats(recent_1d)
        previous_stats = compute_period_stats(previous_6d)
        
        # 增长率计算
        def compute_growth(current, previous):
            if previous == 0:
                return 100 if current > 0 else 0
            return round((current - previous) / previous * 100, 2)
        
        growth = {
            "events": compute_growth(recent_stats["total"], previous_stats["total"]),
            "success_rate": compute_growth(recent_stats["success"], previous_stats["success"]) if previous_stats["success"] > 0 else 0,
            "tokens": compute_growth(recent_stats["tokens"], previous_stats["tokens"]) if previous_stats["tokens"] > 0 else 0,
        }
        
        result = {
            "top_actions": [{"action": action, "count": count} for action, count in top_actions],
            "peak_hour": peak_hour,
            "model_preference": model_stats,
            "error_rates": error_rates,
            "slowest_model": slowest_model,
            "slowest_model_avg_latency": round(max_avg_latency, 2) if slowest_model else 0,
            "7_day_comparison": {
                "recent_1d": recent_stats,
                "previous_6d": previous_stats,
                "growth": growth,
            },
        }
        
        # 缓存结果
        self._cache[cache_key] = result
        self._cache_ttl[cache_key] = time.time()
        
        return result
    
    def recent_events(self, limit: int = 50, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取最近事件"""
        events = list(self._events)
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        
        # 按时间倒序
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return events[:limit]


# 全局单例
USAGE_STATS = UsageStats()