/**
 * 3.3 深度补充：图表类型归一化 —— 反例测试
 * 与 DashboardPage.tsx 中 normChartType / isKpiChart / isTableChart / kpiSpanFor 等价。
 *
 * 反例依据（后端三处归一化）：
 *   action_executor.CHART_TYPE_MAPPING: "KPI": "kpi", "KPI卡": "kpi"
 *   intent_classifier.py:568:           "kpi"/"KPI"/"指标卡"/"指标" → "kpi"
 *   lineage_service.py:631:            str(type).lower() == "kpi"
 */
const CHART_TYPE_ALIAS = {
  kpi: 'kpi',
  'kpi卡': 'kpi',
  'kpi卡片': 'kpi',
  指标卡: 'kpi',
  指标: 'kpi',
  表格: 'table',
};

function normChartType(c) {
  const raw = String((c && (c.chart_type != null ? c.chart_type : c.type)) ?? '')
    .trim()
    .toLowerCase();
  if (!raw) return '';
  return CHART_TYPE_ALIAS[raw] ?? raw;
}
const isKpiChart = c => normChartType(c) === 'kpi';
const isTableChart = c => normChartType(c) === 'table';

/** 旧判定（修复前），用于对照 */
const oldIsKpi = c => c?.chart_type === 'kpi' || c?.type === 'kpi';

function kpiSpanFor(index, total) {
  const spanFor = perRow => {
    const full = Math.floor(total / perRow) * perRow;
    const inRow = index < full ? perRow : total % perRow || perRow;
    return Math.round(24 / inRow);
  };
  return { xs: 24, sm: spanFor(2), lg: spanFor(4) };
}

let fails = 0;
function eq(name, actual, expected) {
  const ok = actual === expected;
  if (!ok) fails++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  → ${JSON.stringify(actual)}${ok ? '' : ' (期望 ' + JSON.stringify(expected) + ')'}`);
}

console.log('=== A. normChartType 归一化 ===\n');
eq('A1 chart_type=kpi', normChartType({ chart_type: 'kpi' }), 'kpi');
eq('A2 type=kpi（后端 s3 引擎写法）', normChartType({ type: 'kpi' }), 'kpi');
eq('A3 chart_type=KPI（反例·大写）', normChartType({ chart_type: 'KPI' }), 'kpi');
eq('A4 chart_type=" KPI "（反例·带空格）', normChartType({ chart_type: ' KPI ' }), 'kpi');
eq('A5 type=KPI卡（反例·中文别名）', normChartType({ type: 'KPI卡' }), 'kpi');
eq('A6 type=指标卡（反例·中文别名）', normChartType({ type: '指标卡' }), 'kpi');
eq('A7 chart_type=指标（反例·中文别名）', normChartType({ chart_type: '指标' }), 'kpi');
eq('A8 type=表格', normChartType({ type: '表格' }), 'table');
eq('A9 chart_type=TABLE（反例·大写）', normChartType({ chart_type: 'TABLE' }), 'table');
eq('A10 空对象', normChartType({}), '');
eq('A11 普通图不被误判', normChartType({ chart_type: 'bar' }), 'bar');
eq('A12 折线图不被误判', normChartType({ chart_type: 'line' }), 'line');

console.log('\n=== B. isKpiChart / isTableChart 判定 ===\n');
eq('B1 表格不是 KPI', isKpiChart({ chart_type: 'table' }), false);
eq('B2 空对象不是 KPI', isKpiChart({}), false);
eq('B3 柱状图不是 KPI', isKpiChart({ chart_type: 'bar' }), false);
eq('B4 大写 KPI 是 KPI', isKpiChart({ chart_type: 'KPI' }), true);
eq('B5 表格识别为 table', isTableChart({ chart_type: 'TABLE' }), true);
eq('B6 KPI 不是 table', isTableChart({ chart_type: 'kpi' }), false);

console.log('\n=== C. 混合写法下的 KPI 总数（旧逻辑会漏统计）===\n');
// 真实场景：LLM/不同模块产出的写法混在一起
const charts = [
  { title: '总担保金额', chart_type: 'kpi' },
  { title: '总笔数', type: 'kpi' },
  { title: '平均抵押率', chart_type: 'KPI' },
  { title: '高风险占比', type: '指标卡' },
  { title: '在保余额', chart_type: ' KPI ' },
  { title: '地区分布', chart_type: 'bar' },
  { title: '明细表', chart_type: 'table' },
];
const newCount = charts.filter(isKpiChart).length;
const oldCount = charts.filter(oldIsKpi).length;
console.log(`  图表总数=${charts.length}  新判定 KPI=${newCount}  旧判定 KPI=${oldCount}`);
eq('C1 新判定应数出 5 张 KPI', newCount, 5);
eq('C2 旧判定漏统计（仅 2 张）', oldCount, 2);
if (oldCount === newCount) {
  console.log('  [warn] 旧判定未复现漏统计，反例失效');
}

console.log('\n=== D. 漏统计如何导致列宽算错 ===\n');
console.log('  真实 5 张 KPI（lg 断点，每行最多 4 张）：');
console.log('    正确：', [0, 1, 2, 3, 4].map(i => kpiSpanFor(i, 5).lg).join(', '), '  → 前4张各6，第5张24（占满，无留白）');
console.log('    漏统计为2：', [0, 1].map(i => kpiSpanFor(i, 2).lg).join(', '), '  → 只有2张进KPI层，另3张被当普通图渲染');
eq('D1 n=5 第5张占满整行', kpiSpanFor(4, 5).lg, 24);
eq('D2 n=5 第1张占 1/4', kpiSpanFor(0, 5).lg, 6);

console.log('\n=== E. 末行留白回归（任意 n 都要无空白）===\n');
for (let n = 1; n <= 9; n++) {
  const spans = Array.from({ length: n }, (_, i) => kpiSpanFor(i, n).lg);
  const lastRowStart = Math.floor((n - 1) / 4) * 4;
  const lastRow = spans.slice(lastRowStart);
  const sum = lastRow.reduce((a, b) => a + b, 0);
  const ok = sum === 24;
  if (!ok) fails++;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  n=${n}  spans=[${spans.join(',')}]  末行=${lastRow.join(',')} 和=${sum}${ok ? '' : ' ≠ 24（有留白）'}`);
}

console.log('\nRESULT:', fails === 0 ? 'ALL PASS' : `${fails} FAILED`);
process.exit(fails === 0 ? 0 : 1);
