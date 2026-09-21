/**
 * 1.7 暗色模式（C 范围：图表 + 仪表盘核心）
 * 集中把明/暗主题令牌注入 ECharts option，杜绝暗底下黑字/黑坐标轴不可见。
 * 设计原则：不在各图表分支散落硬编码色值，统一在此处按 CHART_THEMES 注入。
 */
import { CHART_THEMES } from './ThemeProvider';

export type ChartThemeName = 'light' | 'dark';

/**
 * 把主题令牌应用到 ECharts option（原地浅拷贝，不改 series 数据）。
 * 覆盖：调色板 / 背景 / 全局文字色 / 标题 / 图例 / tooltip / 坐标轴(线·标签·分隔线) / visualMap。
 */
export function themeChartOption(option: any, theme: ChartThemeName): any {
  if (!option || !option.series) return option;

  const t = CHART_THEMES[theme];
  const textColor = t.textColor;          // '#333' / '#ddd'
  const axisLineColor = t.axisLineColor;  // '#ddd' / '#444'
  const splitLineColor = t.splitLineColor; // '#f0f0f0' / '#333'
  const isDark = theme === 'dark';

  const themed: any = { ...option };
  themed.color = t.color;
  themed.backgroundColor = t.backgroundColor;
  themed.textStyle = { ...(themed.textStyle || {}), color: textColor };

  // 标题 / 图例：仅补 textStyle.color，保留其余样式
  const withText = (obj: any) =>
    ({ ...(obj || {}), textStyle: { ...((obj || {}).textStyle || {}), color: textColor } });
  if (themed.title) {
    themed.title = Array.isArray(themed.title) ? themed.title.map(withText) : withText(themed.title);
  }
  if (themed.legend) {
    themed.legend = Array.isArray(themed.legend) ? themed.legend.map(withText) : withText(themed.legend);
  }

  // tooltip 暗底高对比
  themed.tooltip = {
    ...(themed.tooltip || {}),
    backgroundColor: isDark ? '#1f1f1f' : '#ffffff',
    borderColor: isDark ? '#303030' : '#f0f0f0',
    textStyle: { ...((themed.tooltip || {}).textStyle || {}), color: textColor },
  };

  // 坐标轴：线色 / 标签色 / 分隔线色（单值或数组统一处理）
  const applyAxis = (ax: any): any => {
    if (!ax) return ax;
    if (Array.isArray(ax)) return ax.map(applyAxis);
    const a = { ...ax };
    a.axisLine = {
      ...(a.axisLine || {}),
      lineStyle: { ...((a.axisLine || {}).lineStyle || {}), color: axisLineColor },
    };
    a.axisLabel = { ...(a.axisLabel || {}), color: textColor };
    a.splitLine = {
      ...(a.splitLine || {}),
      lineStyle: { ...((a.splitLine || {}).lineStyle || {}), color: splitLineColor },
    };
    a.nameTextStyle = { ...(a.nameTextStyle || {}), color: textColor };
    return a;
  };
  themed.xAxis = applyAxis(themed.xAxis);
  themed.yAxis = applyAxis(themed.yAxis);
  if (themed.angleAxis) themed.angleAxis = applyAxis(themed.angleAxis);
  if (themed.radiusAxis) themed.radiusAxis = applyAxis(themed.radiusAxis);

  // visualMap（热力图）文字色
  if (themed.visualMap) {
    const fixVm = (v: any) => ({ ...(v || {}), textStyle: { ...((v || {}).textStyle || {}), color: textColor } });
    themed.visualMap = Array.isArray(themed.visualMap)
      ? themed.visualMap.map(fixVm)
      : fixVm(themed.visualMap);
  }

  return themed;
}
