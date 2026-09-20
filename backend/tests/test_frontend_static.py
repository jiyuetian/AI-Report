"""#8 / #9 前端静态验收：饼图 legend 可滚动 + 验收报告图 containLabel。

这些是前端/静态资源的渲染可读性修复，难以在 pytest 里起浏览器验证，
故以“源码关键配置存在性”做冒烟断言（与代码审查结论一致）。
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHART_RENDERER = REPO / "frontend" / "src" / "components" / "charts" / "ChartRenderer.tsx"
DASHBOARD_PAGE = REPO / "frontend" / "src" / "views" / "dashboard" / "DashboardPage.tsx"
CHARTS_JS = REPO / "ai-report-acceptance-report" / "assets" / "charts.js"


def test_pie_legend_scroll_in_chart_renderer():
    content = CHART_RENDERER.read_text(encoding="utf-8")
    assert ("type: 'scroll'" in content) or ('type: "scroll"' in content)


def test_pie_legend_scroll_in_dashboard_page():
    content = DASHBOARD_PAGE.read_text(encoding="utf-8")
    assert ("type: 'scroll'" in content) or ('type: "scroll"' in content)


def test_acceptance_charts_js_has_contain_label():
    content = CHARTS_JS.read_text(encoding="utf-8")
    assert "containLabel" in content
