# -*- coding: utf-8 -*-
"""B1 回归（night42）：compare_two_periods 对缺失 data 字段的事件不应抛错。

TASK0_AUDIT B1 / Q13 / ISS-059：analytics.compute_stats 曾直接用 e["data"]，
缺字段会 KeyError → 500。已闭环为 e.get("data") or {}。本测试证明缺 data 不崩。
"""
import time

from app.core.analytics import compare_two_periods


def test_compare_two_periods_tolerates_missing_data_field():
    now = time.time()
    events = [
        {"timestamp": now, "success": True},  # 近期，无 data 字段
        {"timestamp": now, "success": False, "data": {"prompt_tokens": 10, "completion_tokens": 5}},
        {"timestamp": now - 10 * 86400, "success": True},  # 上一周期，无 data
    ]
    # 不应抛 KeyError
    result = compare_two_periods(events)
    assert isinstance(result, dict)
    assert "recent_period" in result
    assert result["recent_period"] == "1d"
