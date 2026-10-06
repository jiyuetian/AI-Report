"""#8 / #9 前端静态验收：饼图 legend 可滚动 + 验收报告图 containLabel。

这些是前端/静态资源的渲染可读性修复，难以在 pytest 里起浏览器验证，
故以“源码关键配置存在性”做冒烟断言（与代码审查结论一致）。
"""
import pytest
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
    # 本测试校验前端 acceptance report 的生成产物 charts.js（containLabel 可读性修复）。
    # 该产物由独立的构建/报告生成步骤产出，本 checkout 未跑该步骤时不应判 FAIL——
    # 缺失属环境依赖（非代码回归），故守卫为 skip 而非失败。
    if not CHARTS_JS.exists():
        pytest.skip(f"生成产物缺失，跳过：{CHARTS_JS}")
    content = CHARTS_JS.read_text(encoding="utf-8")
    assert "containLabel" in content
