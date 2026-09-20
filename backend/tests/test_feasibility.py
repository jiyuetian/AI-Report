"""#7 验收 + PRD 第四节「引导话术规范」：可行性检查矩阵。

覆盖 PRD 4.2 各场景：
- 字段不存在 → blocking + 列出可用字段
- 粒度不支持（年数据要月汇总）→ blocking + 建议改粒度
- 图表数量超限 → blocking
- 删除唯一图表 → blocking（看板至少保留一个）
- 用户 override → 降级为可行（用户优先级最高）
"""
from app.core.feasibility_checker import check_feasibility


def _ctx(field_profiles, grain="row", charts=None):
    return {
        "dataset_info": {"field_profiles": field_profiles, "grain": grain},
        "current_config": {"charts": charts or []},
    }


def test_field_missing_blocking_with_suggestion():
    ctx = _ctx(["地区", "产品", "金额"])
    res = check_feasibility("按区域分析", "filter_drill", {}, ctx)
    assert res["feasible"] is False
    assert any(i["type"] == "field_missing" for i in res["issues"])
    assert "可用的字段有" in res["suggestion"]


def test_grain_mismatch_blocking_with_suggestion():
    ctx = _ctx(["日期", "金额"], grain="yearly")
    res = check_feasibility("按月汇总", "change_chart", {}, ctx)
    assert res["feasible"] is False
    assert any(i["type"] == "grain_mismatch" for i in res["issues"])
    assert "年度" in res["suggestion"]


def test_chart_limit_blocking():
    # 代码实际上限为 50 个图（feasibility_checker._check_chart_count: len>=50 才阻断）
    charts = [{"id": f"c{i}"} for i in range(51)]
    ctx = _ctx(["地区", "金额"], charts=charts)
    res = check_feasibility("再加一个图", "add_chart", {}, ctx)
    assert res["feasible"] is False
    assert any(i["type"] == "chart_limit" for i in res["issues"])
    assert "删除" in res["suggestion"]


def test_min_chart_delete_blocking():
    charts = [{"id": "c1"}]
    ctx = _ctx(["地区"], charts=charts)
    res = check_feasibility("删除这个图", "delete_chart", {}, ctx)
    assert res["feasible"] is False
    assert any(i["type"] == "min_chart_required" for i in res["issues"])


def test_override_makes_feasible():
    ctx = _ctx(["日期", "金额"], grain="yearly")
    res = check_feasibility("按月汇总", "change_chart", {}, ctx, override_blocking=True)
    assert res["feasible"] is True
    assert res["can_override"] is True
    assert len(res["overridden_issues"]) > 0
