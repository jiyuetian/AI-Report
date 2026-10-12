"""
night44 Task C1（ISS-097）回归测试：对话口语修饰词清洗。

验证：title_keyword 带「这张/柱状图」等口语修饰时，换图/删图仍能按真实标题命中，
不再因「该澄清」降级（R2「把各月份结案数这张柱状图改成折线图」应命中「各月份结案数」）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.action_executor import ActionExecutor


def _charts():
    return [
        {"id": "c1", "title": "各月份结案数", "chart_type": "bar"},
        {"id": "c2", "title": "地区分布", "chart_type": "pie"},
        {"id": "c3", "title": "销售趋势图", "chart_type": "line"},
    ]


def test_clean_title_keyword_strips_modifiers():
    assert ActionExecutor._clean_title_keyword("各月份结案数这张柱状图") == "各月份结案数"
    assert ActionExecutor._clean_title_keyword("把销售额那张饼图") == "销售额"
    assert ActionExecutor._clean_title_keyword("地区分布这个图") == "地区分布"
    # 真实标题本身不含修饰词时不应被误伤（保留现有可命中行为）
    # 注：孤立尾字「图」会被剥离（去修饰候选），但 _match_chart_by_title 先试原始关键词，
    # 故精确标题「销售趋势图」仍可命中，见 test_match_chart_by_title_hits_with_modifier。
    assert ActionExecutor._clean_title_keyword("销售趋势图") == "销售趋势"
    assert ActionExecutor._clean_title_keyword("各月份结案数") == "各月份结案数"


def test_match_chart_by_title_hits_with_modifier():
    charts = _charts()
    # R2 场景：关键词带「这张/柱状图」，应命中「各月份结案数」
    chart, used = ActionExecutor._match_chart_by_title(charts, "各月份结案数这张柱状图")
    assert chart is not None
    assert chart["id"] == "c1"
    assert used == "各月份结案数"

    # 不含修饰词时仍按原关键词命中（回归保护）
    chart2, _ = ActionExecutor._match_chart_by_title(charts, "销售趋势图")
    assert chart2 is not None and chart2["id"] == "c3"


def test_match_chart_by_title_no_false_match():
    charts = _charts()
    # 完全不同关键词，不应错配，交由上层澄清
    chart, _ = ActionExecutor._match_chart_by_title(charts, "利润预测图")
    assert chart is None


def test_execute_change_chart_matches_modified_keyword():
    """_execute_change_chart 经 _match_chart_by_title 命中带修饰词的目标图，不进澄清分支。"""
    charts = _charts()
    cfg = {"charts": charts}
    ctx: dict = {}
    params = {
        "title_keyword": "各月份结案数这张柱状图",  # 口语修饰
        "target_type": "line",                       # 改成折线图
    }
    result = ActionExecutor._execute_change_chart(params, cfg, ctx)
    assert result.get("success") is True, result
    assert result.get("requires_clarify") is not True
    # 目标图确实被改成了折线图
    assert any(c["id"] == "c1" and c["chart_type"] == "line" for c in cfg["charts"])


def test_execute_delete_chart_matches_modified_keyword():
    """_execute_delete_chart 经去修饰候选命中带修饰词的目标图。"""
    charts = _charts()
    cfg = {"charts": charts}
    ctx: dict = {}
    params = {"title_keyword": "地区分布那张饼图"}
    result = ActionExecutor._execute_delete_chart(params, cfg, ctx)
    assert result.get("success") is True, result
    assert result.get("requires_clarify") is not True
    assert all(c["id"] != "c2" for c in cfg["charts"])
