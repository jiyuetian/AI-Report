/**
 * 图表配置安全网（防白屏）
 * 2026-09-17 取长补短自 InsightDesk（web/src/components/ReportRenderer.jsx 的 sanitizeChartOption）
 *
 * 作用：在把 option 交给 echarts 之前，把 AI/后端可能产出的非法配置收敛为合法配置，
 * 避免 setOption 抛错导致整张卡片 / 整页白屏。典型修复：
 *   - yAxis.type='count'（非法的频数轴）→ 收敛为 'value'
 *   - series.type='histogram'（{value,count} 直方图）→ 转标准柱状图
 *   - 未知 series.type → 兜底为 'bar'
 */
const VALID_AXIS_TYPES = new Set(['value', 'category', 'time', 'log']);
const KNOWN_SERIES_TYPES = new Set([
  'line', 'bar', 'pie', 'scatter', 'effectScatter', 'radar', 'map', 'tree', 'treemap',
  'graph', 'gauge', 'funnel', 'parallel', 'sankey', 'boxplot', 'candlestick', 'heatmap',
  'pictorialBar', 'themeRiver', 'sunburst', 'lines', 'custom',
]);

function sanitizeAxis(ax: any): any {
  if (Array.isArray(ax)) return ax.map(sanitizeAxis);
  if (!ax || typeof ax !== 'object') return ax;
  if (ax.type && !VALID_AXIS_TYPES.has(ax.type)) {
    // 'count' 本意是直方图频数轴 → 收敛为数值轴
    ax.type = 'value';
  }
  return ax;
}

export function sanitizeChartOption(opt: any): any {
  if (!opt || typeof opt !== 'object') return opt;
  opt.xAxis = sanitizeAxis(opt.xAxis);
  opt.yAxis = sanitizeAxis(opt.yAxis);
  if (opt.angleAxis) opt.angleAxis = sanitizeAxis(opt.angleAxis);
  if (opt.radiusAxis) opt.radiusAxis = sanitizeAxis(opt.radiusAxis);

  const series = opt.series;
  if (series) {
    const arr = Array.isArray(series) ? series : [series];
    const cleaned = arr.map((s: any) => {
      if (!s || typeof s !== 'object') return s;
      // 直方图：{ value: 分箱中心, count: 频数 } → 标准柱状图（x 轴为分箱、y 轴为频数）
      const isHist =
        s.type === 'histogram' ||
        (Array.isArray(s.data) &&
          s.data.length > 0 &&
          s.data.every((d: any) => d && typeof d === 'object' && 'count' in d && 'value' in d));
      if (isHist) {
        const data = Array.isArray(s.data) ? s.data : [];
        const xs = data.map((d: any) => (d && typeof d === 'object' ? d.value : d));
        const ys = data.map((d: any) =>
          d && typeof d === 'object' && 'count' in d
            ? d.count
            : d && typeof d === 'object'
              ? d.value
              : d,
        );
        opt.xAxis = {
          type: 'category',
          data: xs.map((v: any) => (typeof v === 'number' ? Number(v.toFixed(3)) : v)),
          name: (opt.xAxis && opt.xAxis.name) || '',
        };
        opt.yAxis = { type: 'value', name: (opt.yAxis && opt.yAxis.name) || '频数' };
        return { ...s, type: 'bar', data: ys };
      }
      if (!KNOWN_SERIES_TYPES.has(s.type)) {
        // 未知系列类型 → 兜底为柱状图，避免 setOption 抛错
        return { ...s, type: 'bar' };
      }
      return s;
    });
    opt.series = Array.isArray(series) ? cleaned : cleaned[0];
  }
  return opt;
}
