"""#9 验收：报告内嵌 ECharts 图必须 containLabel 且饼图 legend 可滚动，避免文字重叠。

对应审计 #8/#9：实时应用已 containLabel，但报告内嵌图 option 缺失 → 轴文字裁切/重叠。
"""
import html as _html
import json
import re

from app.core.report_generator import ReportGenerator


def _render(chart_type, data):
    rg = ReportGenerator(
        db=None,
        dataset_info={"theme": "t", "field_profiles": []},
        dashboard_config={"charts": []},
    )
    return rg._render_echarts(chart_type, "测试图", data)


def _opt_from(html):
    m = re.search(r'data-option="([^"]+)"', html)
    # 报告渲染用 html.escape(quote=True) 把属性内双引号转义为 &quot;，需还原
    return json.loads(_html.unescape(m.group(1)))


def test_bar_has_contain_label_and_scroll_legend():
    html = _render("bar", [{"dim": "A", "val": 1}, {"dim": "B", "val": 2}])
    assert html
    opt = _opt_from(html)
    assert opt["grid"]["containLabel"] is True
    assert opt["legend"]["type"] == "scroll"


def test_line_has_contain_label():
    html = _render("line", [{"dim": "A", "val": 1}, {"dim": "B", "val": 2}])
    opt = _opt_from(html)
    assert opt["grid"]["containLabel"] is True


def test_pie_has_scroll_legend():
    html = _render("pie", [{"cat": "A", "val": 1}, {"cat": "B", "val": 2}])
    opt = _opt_from(html)
    assert opt["series"][0]["type"] == "pie"
    assert opt["legend"]["type"] == "scroll"


def test_empty_data_returns_empty():
    assert _render("bar", []) == ""
