"""全链路联调用例（Task K）— 离线 smoke 集成。

每个用例返回 (passed: bool, detail: str)。抛异常由 runner 捕获记为失败（诚实，不伪造 PASS）。
覆盖：Task G 隔离批量更新 / Task H 派生指标 / Task I 下游重算 / Task J 使用统计 / 路由装配。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple


def _tc_core_routers() -> Tuple[bool, str]:
    """CORE：确认 usage_stats / recalc_queue / metrics / integration 路由均可装配（全链路入口）。"""
    import importlib
    mods = ["app.api.usage_stats", "app.api.recalc_queue", "app.api.metrics", "app.api.integration"]
    for m in mods:
        importlib.import_module(m)
    return True, f"已装配路由模块 {len(mods)} 个"


def _tc_g_isolated_bulk() -> Tuple[bool, str]:
    """Task G：隔离批量更新 dry-run（只读计划，零 DB）。"""
    from app.core.isolated_bulk_update import run_isolated_bulk_update
    r = run_isolated_bulk_update({"dry_run": True, "operations": []})
    assert isinstance(r, dict), "run_isolated_bulk_update 未返回 dict"
    return True, f"isolated_bulk_update -> keys={list(r.keys())}"


def _tc_h_calculate() -> Tuple[bool, str]:
    """Task H：派生指标 calculate 返回确定性 dict（含 value 或诚实 error）。"""
    from app.core.metric_registry import METRIC_REGISTRY
    ms = METRIC_REGISTRY.list_metrics()
    name = ms[0] if ms else "roi"
    r = METRIC_REGISTRY.calculate(name, {}, operation="query")
    assert isinstance(r, dict), "calculate 未返回 dict"
    assert ("value" in r) or ("error" in r), "calculate 返回缺 value/error 键"
    return True, f"calculate({name!r}) -> keys={list(r.keys())}"


def _tc_h_unknown_metric() -> Tuple[bool, str]:
    """Task H：未知指标诚实报错（不编造）。"""
    from app.core.metric_registry import METRIC_REGISTRY
    r = METRIC_REGISTRY.calculate("__no_such_metric__", {})
    assert isinstance(r, dict) and ("error" in r), "未知指标未诚实报错"
    return True, f"unknown -> {r.get('error')}"


def _tc_i_notify() -> Tuple[bool, str]:
    """Task I：事件驱动下游重算 notify 返回 recalc_id。"""
    from app.core.recalc_engine import RECLAC_ENGINE
    r = RECLAC_ENGINE.notify_data_change(
        {"scope": "ROI", "trigger_action": "integration_test", "trigger_source": "test"}
    )
    assert isinstance(r, dict) and r.get("recalc_id"), "notify 未返回 recalc_id"
    return True, f"recalc_id={r.get('recalc_id')}, affected={r.get('affected_count')}"


def _tc_i_graph() -> Tuple[bool, str]:
    """Task I：依赖图解析返回 list（下游指标）。"""
    from app.core.dependency_graph import DependencyGraph
    dg = DependencyGraph()
    r = dg.get_affected_metrics({"scope": "ROI"})
    assert isinstance(r, list), "get_affected_metrics 未返回 list"
    return True, f"affected_metrics 类型={type(r).__name__} len={len(r)}"


def _tc_j_usage() -> Tuple[bool, str]:
    """Task J：使用统计 record + get_stats 按模型聚合生效。"""
    from app.core.usage_stats import USAGE_STATS
    USAGE_STATS.record_event(
        "model_call", "bench-user",
        {"model": "kimi-k3", "prompt_tokens": 10, "completion_tokens": 5},
        success=True, latency_ms=12,
    )
    stats = USAGE_STATS.get_stats("all")
    by_model = stats.get("by_model") or []
    assert any(m.get("model") == "kimi-k3" for m in by_model), "按模型统计未包含 kimi-k3"
    return True, f"by_model 条数={len(by_model)}, total_events={stats['overview']['total_events']}"


CASES: List[Dict[str, object]] = [
    {"id": "TC-CORE-1", "name": "路由装配(全链路入口)", "group": "core", "run": _tc_core_routers},
    {"id": "TC-G-1", "name": "Task G 隔离批量更新 dry-run", "group": "task_g", "run": _tc_g_isolated_bulk},
    {"id": "TC-H-1", "name": "Task H 派生指标计算", "group": "task_h", "run": _tc_h_calculate},
    {"id": "TC-H-2", "name": "Task H 未知指标诚实报错", "group": "task_h", "run": _tc_h_unknown_metric},
    {"id": "TC-I-1", "name": "Task I 下游重算事件触发", "group": "task_i", "run": _tc_i_notify},
    {"id": "TC-I-2", "name": "Task I 依赖图解析", "group": "task_i", "run": _tc_i_graph},
    {"id": "TC-J-1", "name": "Task J 使用统计按模型聚合", "group": "task_j", "run": _tc_j_usage},
]
