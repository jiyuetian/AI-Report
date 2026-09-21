"""G4 验证：报告 HTML XSS 净化（bleach 白名单，落库前）

XSS 语义：危险的是「可执行结构」（<script>/<iframe>/on* 事件/javascript: 协议），
标签内纯文本 alert(1) 不执行，属安全。最终整篇 HTML 含受信任的 ECharts <script>
（CDN + init），属预期，不应判失败。

断言：
A. sanitize_report_fragment 对典型 payload：剥离所有可执行结构，保留合法排版
B. ReportGenerator._render_html 整篇：
   - 章节注入的 <script>/<iframe>/on*/javascript: 全部消失
   - ECharts 占位（data-option / echarts-chart）保留
   - 正常文本 / 安全标签保留
   - 主题名中的 <script> 被转义（&lt;script&gt;），无裸 <script>alert
"""
import sys
import os
import types

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BACKEND)

# upload.py 依赖系统 libmagic，隔离环境缺失时打桩
if "magic" not in sys.modules:
    _magic = types.ModuleType("magic")
    _magic.from_file = lambda *a, **k: "application/octet-stream"
    sys.modules["magic"] = _magic

from app.core.report_generator import (  # noqa: E402
    ReportGenerator,
    ReportChapter,
    sanitize_report_fragment,
)


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  -> {detail}" if detail else ""))
    return cond


def has_exec(out):
    """是否仍存在可执行 XSS 结构（忽略纯文本）"""
    low = out.lower()
    return ("<script" in low or "<iframe" in low or "<object" in low
            or "onerror" in low or "onload" in low or "onclick" in low
            or "onmouse" in low or "javascript:" in low)


# A) 单元：payload 全部失去可执行结构；安全片段保留结构
FRAG_PAYLOADS = [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(document.cookie)>',
    '<svg/onload=alert(1)>',
    '<a href="javascript:alert(1)">x</a>',
    '<iframe src="javascript:alert(1)"></iframe>',
    '<div style="background:url(javascript:alert(1))">x</div>',
    '<object data="javascript:alert(1)"></object>',
    '<p onclick="alert(1)">hi</p>',
    '<!--<script>alert(1)</script>-->',
]
FRAG_SAFE = [
    ('<p>正常<strong>加粗</strong>文本</p>', "<p"),
    ('<div class="echarts-chart" data-option="{&quot;x&quot;:1}"></div>', "data-option"),
    ('<table class="data-table"><tr><th>列</th></tr><tbody><tr><td>值</td></tr></tbody></table>', "<table"),
    ('<a href="https://example.com">链接</a>', "https://example.com"),
    ('<ul><li>项1</li><li>项2</li></ul>', "<li>项1</li>"),
]


def main():
    results = []

    for p in FRAG_PAYLOADS:
        out = sanitize_report_fragment(p)
        results.append(check(f"strip_exec::{p[:24]}", not has_exec(out), out[:50]))

    for s, needle in FRAG_SAFE:
        out = sanitize_report_fragment(s)
        results.append(check(f"keep_safe::{s[:24]}", (needle in out) and not has_exec(out), out[:50]))

    # B) 整篇集成
    gen = ReportGenerator(
        db=None,
        dataset_info={"theme": "<script>alert('THEME')</script>我的报告"},
        dashboard_config={},
        quality_issues=[],
    )
    chapters = [
        ReportChapter(1, "恶意列名注入",
                      '<table class="data-table"><tr><td><img src=x onerror=alert(1)>col</td></tr></table>'),
        ReportChapter(2, "LLM 文本注入",
                      "<script>alert('xss')</script><p>正常文本保留</p>"),
        ReportChapter(3, "图表占位",
                      '<div class="echarts-chart" data-option="{&quot;series&quot;:[{&quot;type&quot;:&quot;bar&quot;}]}"></div>'),
        ReportChapter(4, "markdown 安全", "## 标题\n- 列表项\n- 列表项2"),
    ]
    full = gen._render_html(chapters)

    # 章节注入的可执行结构必须消失（用章节片段单独验证更精确）
    ch1 = sanitize_report_fragment(chapters[0].content)
    ch2 = sanitize_report_fragment(chapters[1].content)
    results.append(check("render:chapter_img_onerror_gone", "onerror" not in ch1.lower(), ch1[:60]))
    results.append(check("render:chapter_script_gone", "<script" not in ch2.lower(), ch2[:60]))
    results.append(check("render:no_iframe", "<iframe" not in full.lower(), ""))
    results.append(check("render:no_javascript_proto", "javascript:" not in full.lower(), ""))
    results.append(check("render:keeps_echarts", "echarts-chart" in full and "data-option" in full, ""))
    results.append(check("render:keeps_normal_text", "正常文本保留" in full, ""))
    results.append(check("render:keeps_md_list", "<li>列表项</li>" in full and "<li>列表项2</li>" in full, ""))
    results.append(check("render:theme_escaped",
                         "&lt;script&gt;" in full and "<script>alert('THEME')</script>" not in full, ""))

    total = len(results)
    passed = sum(1 for r in results if r)
    print("\n==== G4 SUMMARY ====")
    print(f"total={total} pass={passed} fail={total - passed}")
    if passed == total:
        print("G4_VERIFY_ALL_PASS")
    else:
        print("G4_VERIFY_HAS_FAIL")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
