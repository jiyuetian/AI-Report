"""S3 图表选择策略验收：S3>=6 且全字段可解析不变量 + 0 可视化字段提示（P1）"""
import pytest

from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine


def test_s3_invariant_met_for_rich_dataset():
    eng = S3ChartEngine()
    fields = ["销售日期", "销售额", "地区", "产品"]
    sample = [
        {"销售日期": "2024-01-01", "销售额": 100, "地区": "华东", "产品": "A"},
        {"销售日期": "2024-01-02", "销售额": 120, "地区": "华北", "产品": "B"},
        {"销售日期": "2024-01-03", "销售额": 90, "地区": "华南", "产品": "A"},
        {"销售日期": "2024-01-04", "销售额": 110, "地区": "华东", "产品": "C"},
    ]
    cfg = eng.generate_dashboard_config(fields, grain="detail", sample_data=sample)
    sp = cfg["selection_policy"]
    # 不变量：所有推荐图表引用的字段都真实存在于数据集中
    assert sp["all_fields_parseable"] is True
    # 不变量：chart_count >= min(6, 数据可支撑上限)
    assert cfg["chart_count"] >= min(6, sp["achievable_when_data_allows"])
    assert sp["met_invariant"] is True


def test_zero_chartable_fields_marks_suggestion():
    """纯文本字段数据集：应标记 no_chartable_fields 并给出补充字段建议，而非静默成功。"""
    eng = S3ChartEngine()
    cfg = eng.generate_dashboard_config(
        ["摘要文本", "说明备注"], grain="detail",
        sample_data=[{"摘要文本": "x", "说明备注": "y"}],
    )
    assert cfg["no_chartable_fields"] is True
    assert cfg["chart_count"] == 0
    assert cfg["suggestion"]
    assert "数值" in cfg["suggestion"] or "分类" in cfg["suggestion"]


def test_selection_policy_excludes_unparseable_charts():
    """即使规则引擎推荐了图表，引用了不存在字段的也应被剔除（selection_policy 保证全可解析）。"""
    eng = S3ChartEngine()
    fields = ["销售额", "地区"]
    sample = [{"销售额": 100, "地区": "华东"}, {"销售额": 120, "地区": "华北"}]
    cfg = eng.generate_dashboard_config(fields, grain="detail", sample_data=sample)
    # 不变量：全字段可解析
    assert cfg["selection_policy"]["all_fields_parseable"] is True
    # 实际返回的图表不得引用数据集外字段
    field_set = set(fields)
    for c in cfg["charts"]:
        refs = {c.get("x_field"), c.get("y_field"), c.get("category_field"), c.get("value_field")}
        refs.discard(None)
        assert refs.issubset(field_set), f"图表引用了不存在字段: {refs - field_set}"
