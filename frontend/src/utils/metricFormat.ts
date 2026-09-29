/**
 * 统一数值 / 比率格式化工具（night11 Item3 · ISS-046/047/048）
 *
 * 判定依据（与后端 _is_ratio_field 对齐）：字段名含「率」或以 _rate / ratio 结尾 → 视为比率字段。
 * - 比率字段：按百分比展示（v × 100，保留 2-4 位小数、去尾零，如 0.0004 → 0.04%）
 * - 其余数值：大数走 亿/万 紧凑，小数保留 2 位去尾零（避免被 Math.round 成 0，或裸奔 17 位小数）
 *
 * 覆盖：KPI 卡 / 柱标签 / 坐标轴 / 直方图分桶标签 / 明细表 / tooltip。
 * 单一事实来源，前后端共用同一判定规则。
 */

/** 比率字段判定：含「率」或以 _rate / ratio 结尾（大小写不敏感） */
export const RATIO_FIELD_RE = /率|_rate$|ratio$/i;

export function isRatioField(name?: string | null): boolean {
  if (!name) return false;
  return RATIO_FIELD_RE.test(name);
}

/** 去掉数值格式化后的尾零 / 多余小数点（'0.40' → '0.4'，'100.' → '100'） */
export function trimNum(x: string): string {
  return x.replace(/\.?0+$/, '').replace(/\.$/, '');
}

/**
 * 比率值 → 百分比字符串。v×100，默认保留最多 maxDecimals 位小数（去尾零）。
 * 例：formatPercent(0.0004) → '0.04%'，formatPercent(2.42) → '242%'
 */
export function formatPercent(v: number, maxDecimals = 4): string {
  if (typeof v !== 'number' || isNaN(v)) return '--';
  const pct = v * 100;
  return trimNum(pct.toFixed(maxDecimals)) + '%';
}

/**
 * 紧凑数值（非比率）：亿 / 万 / 小数。
 * 极小数值（0 < |v| < 1）保留 4 位小数，避免被整数化（ histograms 0~0 根因）。
 */
export function formatCompactNum(v: number): string {
  if (typeof v !== 'number' || isNaN(v)) return '--';
  const a = Math.abs(v);
  const fmtFloat = (x: number): string => trimNum(x.toFixed(2));
  if (a >= 1e8) return trimNum((v / 1e8).toFixed(2)) + '亿';
  if (a >= 1e4) return trimNum((v / 1e4).toFixed(2)) + '万';
  if (a > 0 && a < 1) return trimNum(v.toFixed(4));
  return fmtFloat(v);
}

/**
 * 坐标轴 / 柱标签 / tooltip / 明细单元格 统一入口：
 * 率类 → 百分比；否则 → 紧凑数值。
 */
export function formatMetricDisplay(field: string | undefined, v: number): string {
  if (typeof v !== 'number' || isNaN(v)) return String(v ?? '--');
  if (isRatioField(field)) return formatPercent(v);
  return formatCompactNum(v);
}

/**
 * KPI 卡片值格式化：返回 { value, prefix?, suffix? }
 * - cfg.ratio 或 cfg.format==='percent' 或 字段名命中比率 → 百分比（v×100 + %）
 * - cfg.format==='currency' → ¥ 紧凑（亿/万）
 * - 其余 → 紧凑数值（value 已含 亿/万，prefix 不重复）
 */
export function formatKpiValue(
  field: string | undefined,
  val: number,
  cfg?: { format?: string; ratio?: boolean; prefix?: string; suffix?: string; alreadyPercent?: boolean }
): { value: any; prefix?: string; suffix?: string } {
  if (typeof val !== 'number' || isNaN(val)) return { value: '--' };
  const isPercent = cfg?.format === 'percent' || cfg?.ratio === true || isRatioField(field);
  if (isPercent) {
    // 派生指标公式已含「× 100」时，值本身就是百分数（如 抵押率=42.5），不要再乘 100
    if (cfg?.alreadyPercent) {
      return { value: trimNum(val.toFixed(2)), suffix: '%' };
    }
    return { value: trimNum((val * 100).toFixed(4)), suffix: '%' };
  }
  if (cfg?.format === 'currency') {
    const a = Math.abs(val);
    if (a >= 1e8) return { value: trimNum((val / 1e8).toFixed(2)) + '亿', prefix: '¥' };
    if (a >= 1e4) return { value: trimNum((val / 1e4).toFixed(2)) + '万', prefix: '¥' };
    return { value: trimNum(val.toFixed(2)), prefix: '¥' };
  }
  return { value: formatCompactNum(val) };
}
