"""
AI 使用统计 - 分析工具（night17 Task J-8）
纯函数式分析工具，无状态，可单测
"""

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict


def compute_linear_slope(values: List[float], timestamps: List[float]) -> float:
    """计算线性斜率（最小二乘法）"""
    if len(values) != len(timestamps) or len(values) < 2:
        return 0.0
    
    n = len(values)
    sum_x = sum(timestamps)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(timestamps, values))
    sum_x2 = sum(x * x for x in timestamps)
    
    # 避免除以零
    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return 0.0
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope


def bucket_events(events: List[Dict[str, Any]], 
                 time_range: str = "1h", 
                 bucket_size: int = 1) -> Dict[str, int]:
    """按时间分桶统计事件"""
    if not events:
        return {}
    
    end_time = time.time()
    if time_range == "1h":
        start_time = end_time - 3600
    elif time_range == "24h":
        start_time = end_time - 86400
    elif time_range == "7d":
        start_time = end_time - 7 * 86400
    else:
        start_time = end_time - 3600
    
    # 确定桶大小（分钟）
    bucket_minutes = bucket_size
    
    # 计算桶数量
    total_minutes = int((end_time - start_time) / 60)
    num_buckets = total_minutes // bucket_minutes
    
    # 初始化桶
    buckets = {f"bucket_{i}": 0 for i in range(num_buckets)}
    
    # 分桶统计
    for event in events:
        if event["timestamp"] < start_time:
            continue
            
        # 计算事件所在桶的索引
        minutes_since_start = int((event["timestamp"] - start_time) / 60)
        bucket_index = minutes_since_start // bucket_minutes
        
        if 0 <= bucket_index < num_buckets:
            buckets[f"bucket_{bucket_index}"] += 1
    
    return buckets


def compare_two_periods(events: List[Dict[str, Any]], 
                      recent_period: str = "1d", 
                      previous_period: str = "6d") -> Dict[str, Dict[str, Any]]:
    """比较两个时间段的数据"""
    end_time = time.time()
    
    # 计算时间段
    if recent_period == "1d":
        recent_start = end_time - 86400
    elif recent_period == "7d":
        recent_start = end_time - 7 * 86400
    else:
        recent_start = end_time - 86400
    
    if previous_period == "6d":
        previous_start = recent_start - 6 * 86400
        previous_end = recent_start
    elif previous_period == "1w":
        previous_start = recent_start - 7 * 86400
        previous_end = recent_start
    else:
        previous_start = recent_start - 6 * 86400
        previous_end = recent_start
    
    # 过滤事件
    recent_events = [e for e in events if recent_start <= e["timestamp"] <= end_time]
    previous_events = [e for e in events if previous_start <= e["timestamp"] <= previous_end]
    
    # 计算统计数据
    def compute_stats(events_list):
        if not events_list:
            return {"total": 0, "success": 0, "tokens": 0}
        
        total = len(events_list)
        success = sum(1 for e in events_list if e["success"])
        tokens = sum(e["data"].get("prompt_tokens", 0) + e["data"].get("completion_tokens", 0) 
                   for e in events_list)
        
        return {"total": total, "success": success, "tokens": tokens}
    
    recent_stats = compute_stats(recent_events)
    previous_stats = compute_stats(previous_events)
    
    # 计算增长率
    def compute_growth(current, previous):
        if previous == 0:
            return 100 if current > 0 else 0
        return round((current - previous) / previous * 100, 2)
    
    growth = {
        "events": compute_growth(recent_stats["total"], previous_stats["total"]),
        "success_rate": compute_growth(recent_stats["success"], previous_stats["success"]) 
                      if previous_stats["success"] > 0 else 0,
        "tokens": compute_growth(recent_stats["tokens"], previous_stats["tokens"]) 
                if previous_stats["tokens"] > 0 else 0,
    }
    
    return {
        "recent_period": recent_period,
        "previous_period": previous_period,
        "recent_stats": recent_stats,
        "previous_stats": previous_stats,
        "growth": growth,
    }


def get_model_usage_stats(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """获取模型使用统计"""
    model_stats = defaultdict(lambda: {"count": 0, "success": 0, "tokens": 0, "latency": []})
    
    for event in events:
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
    
    detailed_stats = {}
    for model, stats in model_stats.items():
        detailed_stats[model] = {
            "count": stats["count"],
            "success_rate": stats["success"] / stats["count"] if stats["count"] > 0 else 0,
            "total_tokens": stats["tokens"],
            "avg_latency_ms": sum(stats["latency"]) / len(stats["latency"]) if stats["latency"] else 0,
        }
    
    return detailed_stats


def get_action_usage_stats(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """获取动作使用统计"""
    action_stats = defaultdict(lambda: {"count": 0, "success": 0})
    
    for event in events:
        action_type = event["event_type"]
        action_stats[action_type]["count"] += 1
        if event["success"]:
            action_stats[action_type]["success"] += 1
    
    detailed_stats = {}
    for action, stats in action_stats.items():
        detailed_stats[action] = {
            "count": stats["count"],
            "success_rate": stats["success"] / stats["count"] if stats["count"] > 0 else 0,
        }
    
    return detailed_stats


def get_top_models(events: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    """获取最常用的模型"""
    model_stats = get_model_usage_stats(events)
    
    # 按使用次数排序
    sorted_models = sorted(model_stats.items(), key=lambda x: x[1]["count"], reverse=True)
    
    return [{"model": model, "count": stats["count"]} for model, stats in sorted_models[:top_n]]


def get_error_rate_by_model(events: List[Dict[str, Any]]) -> Dict[str, float]:
    """按模型计算错误率"""
    model_stats = get_model_usage_stats(events)
    
    error_rates = {}
    for model, stats in model_stats.items():
        error_rates[model] = round(1 - stats["success_rate"], 4)
    
    return error_rates


def get_peak_usage_hour(events: List[Dict[str, Any]]) -> int:
    """获取高峰使用时段（按小时）"""
    if not events:
        return 0
    
    hourly_usage = defaultdict(int)
    for event in events:
        hour = datetime.fromtimestamp(event["timestamp"]).hour
        hourly_usage[hour] += 1
    
    peak_hour = max(hourly_usage.items(), key=lambda x: x[1])[0]
    return peak_hour


def get_slowest_model(events: List[Dict[str, Any]]) -> Optional[str]:
    """获取最慢的模型"""
    model_latencies = defaultdict(list)
    for event in events:
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
    
    return slowest_model


def get_top_actions(events: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    """获取最常用的动作"""
    action_counts = defaultdict(int)
    for event in events:
        action_counts[event["event_type"]] += 1
    
    top_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"action": action, "count": count} for action, count in top_actions]