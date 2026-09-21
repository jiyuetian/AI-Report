"""3.3 深度补充：图表类型归一化（一次性补丁，可重入）。

反例来源（全仓检索确认，不是臆测）：
- backend/app/core/action_executor.py CHART_TYPE_MAPPING: "KPI": "kpi", "KPI卡": "kpi"
- backend/app/core/intent_classifier.py:568: "kpi"/"KPI"/"指标卡"/"指标" → "kpi"
- backend/app/core/lineage_service.py:631: str(cit.get("type")).lower() == "kpi"
  → 说明真实链路里确实存在大写 / 中文别名的图表类型。

前端旧判定 `c?.chart_type === 'kpi' || c?.type === 'kpi'` 大小写敏感且不认中文别名，
反例：chart_type='KPI' 的卡片会被漏出 KPI 层 → ① 列宽按更小总数算（留白回归）
② 被当普通图渲染（switch 落到 default）③ 详情弹窗判定错误。
"""
import io
import sys

P = 'frontend/src/views/dashboard/DashboardPage.tsx'
s = io.open(P, encoding='utf-8').read()
orig = s
applied = []


def sub(old, new, tag):
    global s
    if s.count(old) != 1:
        print('[fail] %s count=%d' % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new)
    applied.append(tag)


# ---------- 1) 归一化器替换 isKpiChart ----------
OLD_1 = """function isKpiChart(c: any): boolean {
  return c?.chart_type === 'kpi' || c?.type === 'kpi';
}"""
NEW_1 = """/** 图表类型别名表：与后端三处归一化保持一致
 *  - action_executor.CHART_TYPE_MAPPING: KPI / KPI卡 → kpi
 *  - intent_classifier: kpi / KPI / 指标卡 / 指标 → kpi
 *  - lineage_service: str(type).lower() == 'kpi'（说明真实数据存在大写）
 */
const CHART_TYPE_ALIAS: Record<string, string> = {
  kpi: 'kpi',
  'kpi卡': 'kpi',
  'kpi卡片': 'kpi',
  指标卡: 'kpi',
  指标: 'kpi',
  表格: 'table',
};

/** 归一化图表类型：兼容 chart_type / type 两种字段，去空格 + 转小写 + 中文别名 */
function normChartType(c: any): string {
  const raw = String(c?.chart_type ?? c?.type ?? '').trim().toLowerCase();
  if (!raw) return '';
  return CHART_TYPE_ALIAS[raw] ?? raw;
}

function isKpiChart(c: any): boolean {
  return normChartType(c) === 'kpi';
}

/** 表格类同样需要归一化，否则 type='表格' 会被漏进图表层 */
function isTableChart(c: any): boolean {
  return normChartType(c) === 'table';
}"""
if 'function normChartType' in s:
    print('[skip] step1 already applied')
elif s.count(OLD_1) != 1:
    print('[fail] step1 count=%d' % s.count(OLD_1))
    sys.exit(1)
else:
    sub(OLD_1, NEW_1, 'step1 normChartType')

# ---------- 2) 覆盖率统计：排除 KPI 也要归一化 ----------
OLD_2 = "if (c.chart_type !== 'kpi') covered.add(c.x_field || c.category_field || '');"
NEW_2 = "if (!isKpiChart(c)) covered.add(c.x_field || c.category_field || '');"
if 'if (!isKpiChart(c)) covered.add' in s:
    print('[skip] step2 already applied')
else:
    sub(OLD_2, NEW_2, 'step2 covered')

# ---------- 3) 渲染 switch：按归一化类型分支 ----------
OLD_3 = "    switch (chart_type) {\n      case 'kpi':"
NEW_3 = "    switch (normChartType(chart)) {\n      case 'kpi':"
if 'switch (normChartType(chart))' in s:
    print('[skip] step3 already applied')
else:
    sub(OLD_3, NEW_3, 'step3 switch')

# ---------- 4) 图表层排除 table 也归一化 ----------
OLD_4 = "const nonKpiCharts = effectiveCharts.filter(c => !isKpiChart(c) && c.chart_type !== 'table');"
NEW_4 = "const nonKpiCharts = effectiveCharts.filter(c => !isKpiChart(c) && !isTableChart(c));"
if '!isKpiChart(c) && !isTableChart(c)' in s:
    print('[skip] step4 already applied')
else:
    sub(OLD_4, NEW_4, 'step4 nonKpi')

# ---------- 5) 详情弹窗两处判定 ----------
OLD_5 = "{detailChart.chart_type !== 'kpi' && detailChart.chart_type !== 'table' ? ("
NEW_5 = "{!isKpiChart(detailChart) && !isTableChart(detailChart) ? ("
if '!isKpiChart(detailChart) && !isTableChart(detailChart) ? (' in s:
    print('[skip] step5a already applied')
else:
    sub(OLD_5, NEW_5, 'step5a detail-if')

OLD_6 = "<Empty description={detailChart.chart_type === 'kpi' ? 'KPI 指标卡，无独立图表' : '明细表，无独立图表'} />"
NEW_6 = "<Empty description={isKpiChart(detailChart) ? 'KPI 指标卡，无独立图表' : '明细表，无独立图表'} />"
if "isKpiChart(detailChart) ? 'KPI 指标卡" in s:
    print('[skip] step5b already applied')
else:
    sub(OLD_6, NEW_6, 'step5b detail-empty')

io.open(P, 'w', encoding='utf-8').write(s)
print('applied =', applied)
print('changed =', s != orig, 'len =', len(s))
