/**
 * M2-10 看板页 - 渲染真实AI生成的图表
 * L1 KPI卡 + L2趋势/分布/对比 + L3明细 + 右侧血缘问答
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Row, Col, Card, Statistic, Badge, Spin, Empty, Table, message, Typography, Breadcrumb, Modal, Descriptions, Button, Space } from 'antd';
import ReactECharts from 'echarts-for-react';
import { WarningOutlined, RiseOutlined, FallOutlined, ArrowLeftOutlined, BulbOutlined } from '@ant-design/icons';
import { http } from '../../utils/request';
import './DashboardPage.css';
import ChatPanel from '../../components/chat/ChatPanel';
import AppendixPanel from '../../components/appendix/AppendixPanel';
import DashboardOps from './DashboardOps';
import { sanitizeChartOption } from '../../components/charts/sanitizeChartOption';
import ChartErrorBoundary from '../../components/charts/ChartErrorBoundary';

// KPI卡片组件
interface KPICardProps {
  title: string;
  value: string | number;
  prefix?: string;
  suffix?: string;
  change?: number;
  trend?: 'up' | 'down' | 'stable';
  warning?: boolean;
  warningText?: string;
}

const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  prefix = '',
  suffix = '',
  change = 0,
  trend = 'stable',
  warning = false,
  warningText = '',
}) => {
  const trendIcon = trend === 'up' ? <RiseOutlined style={{color: '#52c41a'}} /> : 
                   trend === 'down' ? <FallOutlined style={{color: '#ff4d4f'}} /> : null;

  // 金额过长时自适应缩小字号，避免数字溢出卡片
  const displayText = `${prefix ?? ''}${value ?? ''}${suffix ?? ''}`;
  const len = String(displayText).length;
  const valueFont = len >= 16 ? 20 : len >= 11 ? 24 : 28;

  return (
    <Card 
      className={`kpi-card ${warning ? 'kpi-card-warning' : ''}`}
      bordered={false}
    >
      {/* 预警角标 */}
      {warning && (
        <Badge 
          count={<WarningOutlined />} 
          className="warning-badge"
          style={{backgroundColor: '#ff4d4f'}}
        />
      )}
      
      <div className="kpi-content">
        <div className="kpi-header">
          <span className="kpi-title">{title}</span>
          {trendIcon}
        </div>
        
        <div className="kpi-value">
          <Statistic 
            value={value}
            prefix={prefix}
            suffix={suffix}
            valueStyle={{fontSize: valueFont, fontWeight: 'bold', whiteSpace: 'nowrap'}}
          />
        </div>
        
        {/* 变化率 */}
        {change !== 0 && (
          <div className={`kpi-change ${change > 0 ? 'positive' : 'negative'}`}>
            {change > 0 ? '+' : ''}{change}% 环比
          </div>
        )}
        
        {/* 预警文字 */}
        {warning && warningText && (
          <div className="warning-text">
            <WarningOutlined /> {warningText}
          </div>
        )}
      </div>
    </Card>
  );
};

// 图表数据接口
interface ChartConfig {
  chart_type: string;
  title: string;
  x_field?: string;
  y_field?: string;
  category_field?: string;
  value_field?: string;
  config?: any;
}

interface DashboardConfig {
  charts: ChartConfig[];
  theme: string;
  score: number;
  analysis_text?: string;
}

// ======== 稳健图表数据解析 helper（弱化 LLM 字段映射不准的影响）========

/** 把任意日期样字符串规约为 YYYY-MM（无法识别返回 null） */
function guessMonth(v: any): string | null {
  const s = String(v ?? '').trim();
  if (!s) return null;
  // YYYY年MM月DD日
  let m = s.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日?$/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}`;
  // YYYY年MM
  m = s.match(/^(\d{4})年(\d{1,2})月?$/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}`;
  // YYYY-MM-DD / YYYY/MM/DD
  m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T].*)?$/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}`;
  // YYYY-MM
  m = s.match(/^(\d{4})[-/年](\d{1,2})$/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}`;
  // YYYY-MM-DD 末尾带中文
  m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[\u4e00-\u9fff ]+$/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}`;
  if (/^\d{4}$/.test(s)) return s;
  return null;
}

/** 数值字段集合 */
function numericFieldSet(chartData: any): Set<string> {
  return new Set(Object.keys(chartData?.numeric_stats || {}));
}

/** 是否为"风险/异常"取值（用于文本指标计算比率） */
function isRiskValue(v: any): boolean {
  const s = String(v ?? '').trim();
  if (!s || s === '未知') return false;
  if (s.includes('正常') || s.includes('按时') || s.includes('健康')) return false;
  return true;
}

/** 派生指标口径提示（如「抵押率 = 贷款金额 ÷ 抵押物评估价值（匹配率 98%，按均值汇总）」） */
function derivedMetricHint(chart: any): string {
  const dm = chart?.config?.derived_metric;
  if (!dm || !dm.expression) return '';
  const ratio = dm.match_ratio ? `，匹配率 ${Math.round(dm.match_ratio * 100)}%` : '';
  const aggText = dm.aggregation === 'avg' ? '，按均值汇总' : '';
  return `派生指标：${dm.metric || ''} = ${dm.expression}${ratio}${aggText}`;
}

/**
 * 读取图表声明的聚合方式。
 * S3 生成时若指标是派生比率（如 抵押率 = 贷款金额 ÷ 抵押物评估价值），
 * 会把 aggregation 写成 avg —— 比率求和没有业务意义，这里必须遵从。
 */
function aggOf(chart: any): 'sum' | 'avg' | 'max' | 'min' | 'count' {
  const c = chart?.config || {};
  const raw = String(c.aggregate || c.aggregation || chart?.aggregate || chart?.aggregation || 'sum').toLowerCase();
  if (raw === 'avg' || raw === 'mean' || raw === 'average') return 'avg';
  if (raw === 'max') return 'max';
  if (raw === 'min') return 'min';
  if (raw === 'count') return 'count';
  return 'sum';
}

/** 按聚合口径汇总一组数值（默认 sum，保持历史行为不变） */
function aggregateValues(vals: number[], agg: string): number {
  if (!vals.length) return 0;
  if (agg === 'avg') return vals.reduce((a, b) => a + b, 0) / vals.length;
  if (agg === 'max') return Math.max(...vals);
  if (agg === 'min') return Math.min(...vals);
  if (agg === 'count') return vals.length;
  return vals.reduce((a, b) => a + b, 0);
}

/** 去掉数值格式化后的尾零/小数点 */
function trimNum(x: string): string {
  return x.replace(/\.?0+$/, '').replace(/\.$/, '');
}

/** 为饼图/分布图解析真正的分类维度列名 */
function resolveCategoricalDim(chart: ChartConfig, chartData: any): string | null {
  const title = chart.title || '';
  const x = chart.category_field || chart.x_field || '';
  const numFields = numericFieldSet(chartData);
  const columns = chartData?.columns || [];
  const cand = columns.filter((c: string) => !numFields.has(c));
  if (!cand.length) {
    return columns.includes(x) ? x : columns[0] || null;
  }
  const dist = chartData?.categorical_stats || {};
  if (x && cand.includes(x)) return x;
  const byName = cand.find((c: string) => title.includes(c));
  if (byName) return byName;
  let best: string | null = null;
  let bestS = -Infinity;
  let bestCard = Infinity;
  const kw = ['类型', '分类', '类别', '地区', '区域', '省份', '城市', '状态', '阶段', '担保', '抵押', '贷款', '方式', '性质'];
  for (const c of cand) {
    let s = 0;
    for (const k of kw) {
      if (c.includes(k) && title.includes(k)) s += 4;
    }
    if (/分布|构成|占比|结构|分类|类型/.test(title) && /类型|类别|分类|担保|抵押|地区|贷款|状态|阶段/.test(c)) s += 3;
    if (c === '贷款类型') s += 6;
    if (c === '担保类型') s += 6;
    if (c === '地区' || c === '区域' || c === '省份') s += 4;
    if (/状态|阶段|类别/.test(c) && /状态|阶段|类别/.test(title)) s += 2;
    const card = (dist[c] && dist[c].length) || 0;
    if (s > bestS || (s === bestS && (card < bestCard || bestCard === Infinity))) {
      best = c;
      bestS = s;
      bestCard = card;
    }
  }
  return best || x || columns[0] || null;
}

/** 大数字紧凑格式化（万元/亿元），避免卡片溢出 */
function formatCompact(val: number, fmt?: string): { value: any; prefix?: string; suffix?: string } {
  if (typeof val !== 'number' || isNaN(val)) return { value: '--' };
  const a = Math.abs(val);
  // 小数安全格式化：保留 2 位精度但去掉尾零，避免 258.1791 → "258.179100000000"
  // 这样 258.1791 显示为 258.18、12345 显示为 12,345、258 显示为 258
  const fmtFloat = (v: number): string => trimNum(v.toFixed(2));
  if (fmt === 'currency') {
    const prefix = '¥';
    if (a >= 1e8) return { value: trimNum((val / 1e8).toFixed(2)) + '亿', prefix };
    if (a >= 1e4) return { value: trimNum((val / 1e4).toFixed(2)) + '万', prefix };
    return { value: fmtFloat(val), prefix };
  }
  if (fmt === 'percent') return { value: val, suffix: '%' };
  if (a >= 1e8) return { value: trimNum((val / 1e8).toFixed(2)) + '亿' };
  if (a >= 1e7) return { value: trimNum((val / 1e4).toFixed(1)) + '万' };
  return { value: fmtFloat(val) };
}

/**
  检查图表 option 是否有可绘制的数据点。
  解决"图表标题有但卡片空"（series.data 为空数组时 ECharts 静默渲染空区）的根因。
  任意 series 存在 data 且 length > 0 才算"有数据"。
  */
function hasChartData(option: any): boolean {
  if (!option) return false;
  const series = option.series;
  if (!Array.isArray(series) || series.length === 0) return false;
  return series.some((s: any) => {
    if (!s) return false;
    if (Array.isArray(s.data) && s.data.length > 0) return true;
    // 嵌套数据（treemap/sunburst/boxplot 等）也按 length 判断
    if (s.data && typeof s.data === 'object' && !Array.isArray(s.data)) {
      return Object.keys(s.data).length > 0;
    }
    return false;
  });
}

/** 空数据兜底 ECharts option：画一个居中提示 */
function emptyChartOption(title: string, reason: string): any {
  return {
    title: { text: title, left: 'center', top: '40%', textStyle: { fontSize: 14, color: '#8c8c8c' } },
    graphic: [{
      type: 'text',
      left: 'center',
      top: '52%',
      style: { text: `📊 ${reason}`, fontSize: 14, fill: '#bfbfbf' }
    }],
    series: [],
  };
}

const DashboardPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const urlId = searchParams.get('id') || '';
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [title, setTitle] = useState('看板');
  const [chartData, setChartData] = useState<any>(null);
  // 多数据集图表数据：字段不在主数据集的图表（如"单位所属行业分布"来自画像表）从这里取数
  const [dsDataMap, setDsDataMap] = useState<Record<string, any>>({});
  const [chatCollapsed, setChatCollapsed] = useState(false); // 折叠右侧对话，看板全屏
  const [primaryDs, setPrimaryDs] = useState<string>(''); // 主数据集ID（用于血缘跳转）
  const [detailChart, setDetailChart] = useState<ChartConfig | null>(null); // A03-02-01 图表详情子页

  // 处理AI动作（对话调整）
  const handleAction = useCallback((action: any) => {
    if (!config || !urlId) return;

    const { type, params } = action;

    // 2026-09-18 修复"AI回复成功但页面不变"：
    // 后端动作执行成功时回传权威 new_config（已定位到正确图表、改好类型与字段映射）。
    // 此前端各 case 用 params 自己重算（既会改错图，还会把 chart_type 写成中文"饼图"
    // 导致渲染分支匹配不上、看起来毫无变化），现优先采用后端 new_config 整体替换。
    if (action.new_config && Array.isArray(action.new_config.charts)) {
      setConfig(action.new_config as DashboardConfig);
      return;
    }

    let newConfig = JSON.parse(JSON.stringify(config));
    let changed = false;

    switch (type) {
      case 'change_chart': {
        // 修改图表类型（仅后端未回传 new_config 时的兜底路径）
        const charts = newConfig.charts;
        if (charts.length === 0) break;

        let targetIdx = 0;
        if (params.chart_index !== undefined) {
          targetIdx = params.chart_index - 1;
        } else if (params.target_type) {
          // 找最后一个匹配原始类型的
          const found = charts.findLastIndex((c: any) => c.chart_type !== params.target_type);
          if (found >= 0) targetIdx = found;
        }

        if (targetIdx >= 0 && targetIdx < charts.length) {
          charts[targetIdx].chart_type = normalizedChartType(params.target_type);
          changed = true;
          message.success(`已将图表改为${params.target_type}`);
        }
        break;
      }
      
      case 'add_chart': {
        // 新增图表：优先按后端渲染指令逐张添加（含真实字段，避免抄已有图表造成维度错乱）
        const charts = newConfig.charts;
        const updates = (action.render_updates || []).filter(
          (u: any) => u.type === 'add_chart' && u.chart
        );
        if (updates.length) {
          for (const u of updates) {
            const c = u.chart;
            charts.push({
              id: c.id || `chart_${charts.length + 1}`,
              chart_type: c.chart_type || 'bar',
              title: c.title || '新增图表',
              dataset_id: c.dataset_id || urlId,
              x_field: c.x_field,
              y_field: c.y_field,
              category_field: c.category_field,
              value_field: c.value_field,
              config: c.config || {},
            });
          }
          changed = true;
          message.success(`已添加 ${updates.length} 个图表`);
          break;
        }
        // 兼容旧逻辑（单图，使用 params 真实字段，不再抄已有图表）
        const chartType = params.chart_type || 'bar';
        const legacyChart = {
          id: `chart_${charts.length + 1}`,
          chart_type: chartType,
          title: params.title || `新增${chartType}`,
          dataset_id: params.dataset_id || urlId,
          x_field: params.x_field,
          y_field: params.y_field,
          category_field: params.category_field,
          value_field: params.value_field,
          config: {},
        };
        charts.push(legacyChart);
        changed = true;
        message.success(`已添加${chartType}图表`);
        break;
      }
      
      case 'delete_chart': {
        // 删除图表
        const charts = newConfig.charts;
        if (charts.length <= 1) {
          message.warning('看板至少保留一个图表');
          break;
        }
        
        let targetIdx = charts.length - 1; // 默认删最后一个
        if (params.chart_index !== undefined) {
          targetIdx = params.chart_index - 1;
        } else if (params.chart_type) {
          const normalized = normalizedChartType(params.chart_type);
          const found = charts.findLastIndex((c: any) => c.chart_type === normalized);
          if (found >= 0) targetIdx = found;
        }
        
        if (targetIdx >= 0 && targetIdx < charts.length) {
          const deleted = charts.splice(targetIdx, 1);
          changed = true;
          message.success(`已删除图表${deleted[0].title}`);
        }
        break;
      }
      
      case 'reorder_chart': {
        // 排序调整
        const charts = newConfig.charts;
        if (charts.length < 2) break;
        
        // 默认调整最后一个
        let targetIdx = charts.length - 1;
        if (params.chart_index !== undefined) {
          targetIdx = params.chart_index - 1;
        }
        
        const direction = params.direction;
        if (direction === 'up' && targetIdx > 0) {
          [charts[targetIdx], charts[targetIdx - 1]] = [charts[targetIdx - 1], charts[targetIdx]];
          changed = true;
        } else if (direction === 'down' && targetIdx < charts.length - 1) {
          [charts[targetIdx], charts[targetIdx + 1]] = [charts[targetIdx + 1], charts[targetIdx]];
          changed = true;
        } else if (direction === 'top' && targetIdx > 0) {
          const chart = charts.splice(targetIdx, 1)[0];
          charts.unshift(chart);
          changed = true;
        } else if (direction === 'bottom' && targetIdx < charts.length - 1) {
          const chart = charts.splice(targetIdx, 1)[0];
          charts.push(chart);
          changed = true;
        }
        message.success(`图表已${direction}`);
        break;
      }
      
      case 'edit_title': {
        // 修改标题
        const newTitle = params.new_title;
        if (!newTitle) break;
        
        if (params.chart_id) {
          // 修改图表标题
          const charts = newConfig.charts;
          for (const chart of charts) {
            if (chart.id === params.chart_id) {
              chart.title = newTitle;
              changed = true;
              break;
            }
          }
        } else {
          // 修改看板标题
          setTitle(newTitle);
          changed = true;
        }
        message.success(`标题已更新为${newTitle}`);
        break;
      }

      case 'chart_fix': {
        // AI 已在清洗层真实修复数据（图表取数读的就是清洗层）→ 重新拉取刷新即可见
        const dsId = params.dataset_id || primaryDs;
        if (dsId) {
          http.get<any>(`/datasets/${dsId}/chart-data`)
            .then((res: any) => {
              if (!res) return;
              setDsDataMap(prev => ({ ...prev, [dsId]: res }));
              if (!primaryDs || dsId === primaryDs) setChartData(res);
            })
            .catch(() => { /* 刷新失败不影响对话结果展示 */ });
        }
        if (action.refresh_chart_data) {
          message.success(action.message || '图表已按修复后的数据刷新');
        }
        break;
      }
    }
    
    if (changed) {
      setConfig(newConfig);
      // 保存到后端
      http.patch(`/dashboards/${urlId}`, { config: newConfig })
        .catch((err: any) => console.warn('保存配置到后端失败:', err));
    }
  }, [config, urlId, primaryDs]);
  
  // 标准化图表类型名（中文转英文）
  const normalizedChartType = (typeName: string): string => {
    const mapping: Record<string, string> = {
      '饼图': 'pie', '柱图': 'bar', '柱状图': 'bar',
      '线图': 'line', '折线图': 'line', '散点图': 'scatter',
      '表格': 'table', 'kpi': 'kpi'
    };
    return mapping[typeName] || typeName;
  };

  // 从后端加载看板详情（真实数据）
  useEffect(() => {
    let mounted = true;
    const loadDashboard = async () => {
      try {
        if (!urlId) {
          setLoading(false);
          return;
        }
        
        // 1. 加载看板配置（标题、图表列表）
        const dashboardRes = await http.get<any>(`/dashboards/${urlId}`);
        if (dashboardRes?.name) {
          setTitle(dashboardRes.name);
        }
        if (dashboardRes?.config) {
          setConfig(dashboardRes.config);
        }
        
        // 2. 主数据集ID（详情接口已返回；若缺失则回退到 datasets/dataset_ids）
        const primaryDs =
          dashboardRes.primary_dataset_id ||
          dashboardRes.dataset_ids?.[0] ||
          dashboardRes.datasets?.[0]?.id;
        if (primaryDs) setPrimaryDs(primaryDs);

        // 2b. 多数据集：并行拉取所有数据集的图表数据。
        // 修复（2026-09-17）：此前只取主数据集，跨数据集图表（如"单位所属行业分布"字段在
        // 另一份画像表里）拿主数据集取数全为 undefined → 空图。现全量拉取、按字段归属选数据集。
        const allDsIds: string[] = Array.from(new Set(
          [
            ...(dashboardRes.dataset_ids || []),
            ...((dashboardRes.datasets || []).map((d: any) => d?.id).filter(Boolean)),
            ...(primaryDs ? [primaryDs] : []),
          ].filter(Boolean)
        ));
        const dsMap: Record<string, any> = {};
        if (allDsIds.length > 0) {
          const results = await Promise.all(
            allDsIds.map(id => http.get<any>(`/datasets/${id}/chart-data`).catch(() => null))
          );
          allDsIds.forEach((id, i) => { if (results[i]) dsMap[id] = results[i]; });
          if (mounted) setDsDataMap(dsMap);
        }

        // 3. 主数据集图表数据（优先复用上面已拉取的结果）
        if (primaryDs && dsMap[primaryDs]) {
          setChartData(dsMap[primaryDs]);
        } else if (primaryDs) {
          try {
            const res2 = await http.get<any>(`/datasets/${primaryDs}/chart-data`);
            if (mounted && res2) setChartData(res2);
          } catch { /* 保持 null，渲染层兜底 */ }
        }
      } catch (err: any) {
        if (mounted) {
          message.warning(`看板详情加载失败: ${err?.message || '网络错误'}，将展示默认看板`);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    loadDashboard();
    return () => { mounted = false; };
  }, [urlId]);

  // 有效图表列表：在LLM编排结果基础上，自动补足"贷款类型/地区/担保类型"分布图（如缺失）
  const effectiveCharts = useMemo(() => {
    if (!config) return [];
    const base = config.charts || [];
    if (!chartData?.columns?.length) return base;
    const covered = new Set<string>();
    base.forEach((c: any) => {
      if (c.chart_type !== 'kpi') covered.add(c.x_field || c.category_field || '');
    });
    const want = ['贷款类型', '地区', '担保类型'];
    const auto: any[] = [];
    for (const w of want) {
      if (
        chartData.columns.includes(w) &&
        !covered.has(w) &&
        !base.some((c: any) => (c.title || '').includes(w))
      ) {
        auto.push({ chart_type: 'pie', title: `${w}分布`, x_field: w, _auto: true });
      }
    }
    return auto.length ? [...base, ...auto] : base;
  }, [config, chartData]);

  // 按图表来源数据集取数：a 数据 → 图表1/2/3，b 数据 → 图表4/5/6，各取各的，互不影响。
  // ① 优先用图表自带的 dataset_id（S3 生成时写入，最可靠）
  // ② 老看板没有 dataset_id 才回退按字段归属匹配（兼容历史数据）
  const dataForChart = (chart: any) => {
    if (!chart || !chartData) return chartData;
    const own = chart.dataset_id as string | undefined;
    if (own && dsDataMap[own]) return dsDataMap[own];

    const need = [chart.category_field, chart.x_field, chart.y_field, chart.value_field]
      .filter(Boolean) as string[];
    if (need.length === 0) return chartData;
    if (need.every(f => (chartData.columns || []).includes(f))) return chartData;
    for (const cand of Object.values(dsDataMap)) {
      const c = cand as any;
      if (c?.columns?.length && need.every(f => c.columns.includes(f))) return c;
    }
    return chartData;
  };

  // 空图时给出真实原因，便于定位（而不是笼统提示"无可绘制数据"）
  const chartEmptyReason = (chart: any): string | null => {
    const own = chart?.dataset_id as string | undefined;
    if (own && !dsDataMap[own]) {
      return '该图表的来源数据集已不可用（可能已删除）';
    }
    const cd = dataForChart(chart);
    if (!cd) return '未加载到任何数据集数据';
    const cols: string[] = cd.columns || [];
    const need = [chart?.category_field, chart?.x_field, chart?.y_field, chart?.value_field]
      .filter(Boolean) as string[];
    if (need.length) {
      const missing = need.filter(f => !cols.includes(f));
      if (missing.length === need.length) {
        return `字段「${missing.join('、')}」不在该图表来源数据集中`;
      }
    }
    return null;
  };

  // 根据配置和真实数据生成ECharts option
  const generateChartOption = (chart: ChartConfig) => {
    const cd = dataForChart(chart);
    if (!cd || !cd.data || cd.data.length === 0) {
      return {
        title: { text: chart.title, left: 'center', textStyle: { fontSize: 14 } },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        series: [{
          type: 'empty',
          label: { show: true, formatter: chartEmptyReason(chart) || '暂无数据' }
        }]
      };
    }

    const { chart_type, title, x_field, y_field, category_field, value_field } = chart;
    const data = cd.data;
    const numericStats = cd.numeric_stats;

    switch (chart_type) {
      case 'kpi':
        // KPI 不在这里渲染，单独用KPICard
        return {};
      
      case 'line': {
        // 折线图：x=日期(按月份规约)，y=数值指标；若 y 为文本状态则计算"风险占比"或"计数量"
        const xF = x_field || '';
        const yF = y_field || '';
        const numFields = numericFieldSet(cd);
        const numY = !!yF && numFields.has(yF);

        // 按月份分桶
        const measureMap = new Map<string, number[]>(); // 每个桶的度量样本
        const totalMap = new Map<string, number>();     // 每个桶的总样本数
        let hasDate = false;
        data.forEach((r: any) => {
          const raw = String(r[xF] ?? '').trim();
          const bucket = guessMonth(raw);
          if (bucket) hasDate = true;
          const key = bucket || raw || '未知';
          totalMap.set(key, (totalMap.get(key) || 0) + 1);
          const arr = measureMap.get(key) || [];
          if (numY) {
            const v = parseFloat(String(r[yF] ?? ''));
            if (!isNaN(v)) arr.push(v);
          } else {
            arr.push(isRiskValue(r[yF]) ? 1 : 0);
          }
          measureMap.set(key, arr);
        });

        const keys = Array.from(measureMap.keys()).sort();
        let seriesData: number[];
        let yName: string;
        if (numY) {
          seriesData = keys.map(k => {
            const a = measureMap.get(k)!;
            return a.length ? Math.round((a.reduce((x, y) => x + y, 0) / a.length) * 100) / 100 : 0;
          });
          yName = yF;
        } else {
          const anyRisk = data.some((r: any) => isRiskValue(r[yF]));
          const distinctValues = new Set(data.map((r: any) => String(r[yF] ?? '').trim()).filter(Boolean));
          if (anyRisk && distinctValues.size > 1) {
            seriesData = keys.map(k => {
              const a = measureMap.get(k)!;
              const n = totalMap.get(k) || 1;
              return Math.round((a.filter(x => x === 1).length / n) * 10000) / 100;
            });
            yName = '逾期率(%)';
          } else {
            seriesData = keys.map(k => (totalMap.get(k) || 0));
            yName = '数量';
          }
        }
        if (!hasDate && keys.length <= 1) {
          seriesData = [];
        }

        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'category', data: keys, boundaryGap: false },
          yAxis: { type: 'value', name: yName },
          series: [{
            data: seriesData,
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            lineStyle: { width: 2, color: '#1890ff' },
            areaStyle: { color: 'rgba(24, 144, 255, 0.1)' }
          }]
        };
      }

      case 'bar': {
        // 柱状图：x_field = 分类，y_field = 数值
        // 2026-09-17：此前无条件求和。比率类派生指标（抵押率/逾期率）求和是错误口径，
        // 必须按图表声明的聚合方式（S3 反哺的 avg）来汇总。
        const categoryValues = [...new Set(data.map((r: any) => String(r[category_field || x_field || ''])))]
          .filter(v => v != null && v !== '');
        const groups = new Map<string, number[]>();
        const cntMap = new Map<string, number>();
        data.forEach((r: any) => {
          const cat = String(r[category_field || x_field || '']);
          const val = parseFloat(String(r[value_field || y_field || '']));
          if (!isNaN(val)) {
            if (!groups.has(cat)) groups.set(cat, []);
            (groups.get(cat) as number[]).push(val);
          }
          cntMap.set(cat, (cntMap.get(cat) || 0) + 1);
        });
        const agg = aggOf(chart);
        // 2026-09-17：度量列不可算（维度自指 / 文本列 / aggregation=count）时退化为每类计数，
        // 与饼图取值逻辑保持一致，避免柱状图因 parseFloat 得到 NaN 而整张空白。
        const seriesData = (groups.size > 0 && agg !== 'count')
          ? Array.from(groups.entries()).map(([cat, vals]) => ({
              name: cat, value: aggregateValues(vals, agg)
            }))
          : Array.from(cntMap.entries()).map(([cat, n]) => ({ name: cat, value: n }));
        const xData = seriesData.map(d => d.name);
        const yData = seriesData.map(d => d.value);
        const colors = ['#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452', '#6DC8EC'];
        
        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'category', data: xData },
          yAxis: { type: 'value', name: value_field },
          series: [{
            data: yData,
            type: 'bar',
            itemStyle: { 
              color: (params: any) => colors[params.dataIndex % colors.length]
            },
            label: { show: true, position: 'top' }
          }]
        };
      }

      case 'pie': {
        // 饼图：维度=解析出的真实分类列（避免落到数值列）
        // 有 value_field 时按图表聚合口径汇总（比率类 avg，否则求和）；
        // 无 value_field 时退化为每类计数（构成占比）
        const dim = resolveCategoricalDim(chart, cd) || x_field || '';
        const valField = value_field || y_field || '';
        let seriesData: Array<{ name: string; value: number }> = [];
        let valueMode: 'count' | 'agg' = 'count';
        const agg = aggOf(chart);
        if (valField) {
          const groups = new Map<string, number[]>();
          data.forEach((r: any) => {
            const v = parseFloat(String(r[valField]));
            if (isNaN(v)) return;
            const k = String(r[dim] ?? '').trim() || '未知';
            if (!groups.has(k)) groups.set(k, []);
            (groups.get(k) as number[]).push(v);
          });
          if (groups.size > 0) {
            seriesData = Array.from(groups.entries())
              .map(([name, vals]) => ({ name, value: aggregateValues(vals, agg) }))
              .sort((a, b) => b.value - a.value)
              .slice(0, 8);
            valueMode = 'agg';
          } else {
            seriesData = [];
          }
        }
        if (valueMode === 'count') {
          const cnt = new Map<string, number>();
          data.forEach((r: any) => {
            const v = String(r[dim] ?? '').trim() || '未知';
            cnt.set(v, (cnt.get(v) || 0) + 1);
          });
          seriesData = Array.from(cnt.entries())
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 8);
        }

        return {
          title: { text: `${title}（按${dim}）`, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: {
            trigger: 'item',
            formatter: valueMode === 'count' ? '{b}: {c} 笔 ({d}%)' : '{b}: {c} ({d}%)'
          },
          legend: { type: 'scroll' as const, orient: 'horizontal' as const, bottom: '2%', left: 'center', textStyle: { fontSize: 12 } },
          series: [{
            type: 'pie',
            radius: ['38%', '58%'],
            center: ['50%', '44%'],
            data: seriesData,
            emphasis: {
              itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0, 0.5)' }
            },
            label: { formatter: '{b}\n{d}%' }
          }]
        };
      }

      case 'map': {
        // 地区分布：未注册地理底图时，按「地区维度 + 数值度量」渲染为柱状分布，
        // 与 bar 分支同一套聚合口径（比率类 avg，金额类 sum）
        const geoDim = category_field || (chart.config as any)?.geo_field || '';
        const geoVal = value_field || (chart.config as any)?.value_field || '';
        const agg = aggOf(chart);
        const groups = new Map<string, number[]>();
        const cntMap = new Map<string, number>();
        data.forEach((r: any) => {
          const k = String(r[geoDim] ?? '').trim() || '未知';
          const v = parseFloat(String(r[geoVal]));
          if (!isNaN(v)) {
            if (!groups.has(k)) groups.set(k, []);
            (groups.get(k) as number[]).push(v);
          }
          cntMap.set(k, (cntMap.get(k) || 0) + 1);
        });
        const seriesData = (groups.size > 0 && geoVal && agg !== 'count')
          ? Array.from(groups.entries()).map(([name, vals]) => ({ name, value: aggregateValues(vals, agg) }))
          : Array.from(cntMap.entries()).map(([name, n]) => ({ name, value: n }));
        seriesData.sort((a, b) => b.value - a.value);
        const colors = ['#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452', '#6DC8EC'];
        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'category', data: seriesData.map(d => d.name), axisLabel: { rotate: seriesData.length > 6 ? 30 : 0 } },
          yAxis: { type: 'value', name: geoVal },
          series: [{
            data: seriesData.map(d => d.value),
            type: 'bar',
            itemStyle: { color: (params: any) => colors[params.dataIndex % colors.length] },
            label: { show: true, position: 'top' }
          }]
        };
      }

      case 'histogram': {
        // 数值分布直方图：前端对原始行按值域等宽分箱计数（S3 只给字段不给分箱结果）
        const histVal = value_field || y_field || (chart.config as any)?.field || '';
        const raw = data
          .map((r: any) => parseFloat(String(r[histVal])))
          .filter((v: number) => !isNaN(v));
        if (raw.length === 0) {
          return {
            title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
            series: [{ type: 'empty', label: { show: true, formatter: `字段「${histVal}」无可统计的数值` } }]
          };
        }
        const min = Math.min(...raw);
        const max = Math.max(...raw);
        const binCount = Math.min(15, Math.max(6, Math.round(Math.sqrt(raw.length))));
        const span = (max - min) / binCount || 1;
        const counts: number[] = new Array(binCount).fill(0);
        raw.forEach((v: number) => {
          const idx = Math.min(binCount - 1, Math.floor((v - min) / span));
          counts[idx] += 1;
        });
        const fmt = (n: number) => (Math.abs(n) >= 1e8 ? `${(n / 1e8).toFixed(1)}亿`
          : Math.abs(n) >= 1e4 ? `${(n / 1e4).toFixed(0)}万` : `${Math.round(n)}`);
        const xData = counts.map((_, i) => {
          const lo = min + i * span;
          const hi = lo + span;
          return i === binCount - 1 ? `${fmt(lo)}~${fmt(hi)}` : `${fmt(lo)}~${fmt(hi)}`;
        });
        return {
          title: { text: `${title}（${histVal}）`, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'category', data: xData, axisLabel: { rotate: 30, fontSize: 10 } },
          yAxis: { type: 'value', name: '数量' },
          series: [{
            data: counts,
            type: 'bar',
            itemStyle: { color: '#5B8FF9' },
            label: { show: true, position: 'top' }
          }]
        };
      }

      case 'scatter': {
        // 散点图：x_field 和 y_field 都必须是数值
        const seriesData = data
          .filter((r: any) => {
            const xv = parseFloat(String(r[x_field || '']));
            const yv = parseFloat(String(r[y_field || '']));
            return !isNaN(xv) && !isNaN(yv);
          })
          .map((r: any) => ({
            value: [
              parseFloat(String(r[x_field || ''])),
              parseFloat(String(r[y_field || '']))
            ]
          }));
        
        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'item' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'value', name: x_field },
          yAxis: { type: 'value', name: y_field },
          series: [{
            symbolSize: 8,
            data: seriesData,
            type: 'scatter',
            itemStyle: { color: '#1677ff' }
          }]
        };
      }

      case 'heatmap': {
        // 热力图：两个分类维度 × 一个数值度量（来自 s3_chart_rules.yaml 热力图-矩阵规则：
        // config.x / config.y / config.value）。S3 只给字段名，前端按 (x,y) 聚合出值矩阵。
        const xDim = category_field || (chart.config as any)?.x || x_field || '';
        const yDim = (chart.config as any)?.y || value_field || y_field || '';
        const valF = value_field || (chart.config as any)?.value || y_field || '';
        if (!xDim || !yDim || !valF) {
          return {
            title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
            series: [{ type: 'empty', label: { show: true, formatter: '热力图需「两个分类维度 + 一个数值」字段，当前配置不全' } }]
          };
        }
        const agg = aggOf(chart);
        const cellVal = new Map<string, number[]>();
        const xSet = new Set<string>();
        const ySet = new Set<string>();
        data.forEach((r: any) => {
          const xv = String(r[xDim] ?? '').trim();
          const yv = String(r[yDim] ?? '').trim();
          const v = parseFloat(String(r[valF]));
          if (!xv || !yv || isNaN(v)) return;
          xSet.add(xv);
          ySet.add(yv);
          const key = `${xv}||${yv}`;
          if (!cellVal.has(key)) cellVal.set(key, []);
          (cellVal.get(key) as number[]).push(v);
        });
        const xCats = Array.from(xSet);
        const yCats = Array.from(ySet);
        if (xCats.length === 0 || yCats.length === 0) {
          return {
            title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
            series: [{ type: 'empty', label: { show: true, formatter: '热力图无可用数据（分类/数值字段为空）' } }]
          };
        }
        const heatData: number[][] = [];
        let vmin = Infinity;
        let vmax = -Infinity;
        xCats.forEach((xv, xi) => {
          yCats.forEach((yv, yi) => {
            const vals = cellVal.get(`${xv}||${yv}`);
            const v = vals && vals.length ? aggregateValues(vals, agg) : 0;
            if (v < vmin) vmin = v;
            if (v > vmax) vmax = v;
            heatData.push([xi, yi, v]);
          });
        });
        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { position: 'top', formatter: (p: any) => `${xCats[p.data[0]]} × ${yCats[p.data[1]]}<br/>${valF}: ${p.data[2]}` },
          grid: { left: '3%', right: '4%', bottom: '14%', top: '8%', containLabel: true },
          xAxis: { type: 'category', data: xCats, axisLabel: { rotate: xCats.length > 6 ? 30 : 0, fontSize: 10 } },
          yAxis: { type: 'category', data: yCats, axisLabel: { fontSize: 10 } },
          visualMap: {
            min: isFinite(vmin) ? vmin : 0,
            max: isFinite(vmax) ? vmax : 1,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: 0,
            textStyle: { fontSize: 10 },
          },
          series: [{
            type: 'heatmap',
            data: heatData,
            label: { show: xCats.length * yCats.length <= 60, fontSize: 10 },
            emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' } },
          }],
        };
      }

      case 'table': {
        // 明细表格（不在这里渲染，单独处理）
        return {};
      }

      default:
        return {
          title: { text: title, left: 'center' },
          series: [{ type: chart_type }]
        };
    }
  };

  // 派生KPI值：config.value 缺全省略时，从真实数据按 aggregate 计算
  const deriveKpi = (chart: ChartConfig): { value: any; prefix?: string; suffix?: string; change?: number; trend?: string; warning?: boolean; warningText?: string } => {
    const c = chart.config || {};
    if (c.value !== undefined && c.value !== null) {
      return { value: c.value, prefix: c.prefix, suffix: c.suffix, change: c.change, trend: c.trend, warning: c.warning, warningText: c.warningText };
    }
    const field = chart.y_field || chart.x_field || '';
    const data = chartData?.data || [];
    if (!field) return { value: '--' };
    const nums = data
      .map((r: any) => parseFloat(String(r[field])))
      .filter((v: any) => !isNaN(v));
    if (!nums.length) return { value: '--' };
    // 兼容 S3 反哺的 aggregation（比率类派生指标为 avg，不能求和）
    const agg = aggOf(chart);
    const dm = (c.derived_metric || {}) as any;
    // 反推公式形如「抵押率 = 贷款金额 ÷ 抵押物评估价值 × 100」→ 值已是百分数，补 % 后缀
    const isPercentMetric = !!dm.ratio && /×\s*100/.test(String(dm.expression || dm.formula || ''));
    let val: number;
    if (agg === 'max') val = Math.max(...nums);
    else if (agg === 'min') val = Math.min(...nums);
    else if (agg === 'avg') val = nums.reduce((a: number, b: number) => a + b, 0) / nums.length;
    else if (agg === 'count') val = nums.length;
    else val = nums.reduce((a: number, b: number) => a + b, 0);
    // 大金额紧凑格式化，避免卡片溢出显示不全
    const compact = formatCompact(val, c.format);
    return {
      value: compact.value,
      prefix: compact.prefix ?? (c.format === 'currency' ? '¥' : (c.prefix || '')),
      suffix: compact.suffix ?? ((c.format === 'percent' || isPercentMetric) ? '%' : (c.suffix || '')),
    };
  };

  // 渲染KPI层
  const renderKPILayer = () => {
    if (!config) return null;
    const kpiCharts = effectiveCharts.filter((c: any) => c.chart_type === 'kpi');
    
    if (kpiCharts.length === 0) return null;

    return (
      <div className="kpi-layer">
        <Row gutter={[16, 16]}>
          {kpiCharts.map((chart: ChartConfig, index: number) => {
            const kv = deriveKpi(chart);
            return (
            <Col xs={24} sm={12} lg={6} key={`kpi-${index}`}>
              <KPICard
                title={chart.title}
                value={kv.value}
                prefix={kv.prefix}
                suffix={kv.suffix}
                change={kv.change || 0}
                trend={(kv.trend as any) || 'stable'}
                warning={kv.warning}
                warningText={kv.warningText}
              />
            </Col>
            );
          })}
        </Row>
      </div>
    );
  };

  // 渲染图表层（非KPI）
  const renderChartLayer = () => {
    if (!config) return null;
    const nonKpiCharts = effectiveCharts.filter(c => c.chart_type !== 'kpi' && c.chart_type !== 'table');

    if (nonKpiCharts.length === 0) return null;

    return (
      <div className="evidence-layer">
        <h3 className="layer-title">趋势与对比分析</h3>
        <Row gutter={[16, 16]}>
          {nonKpiCharts.map((chart: ChartConfig, index: number) => {
            // 修复"图表标题有但卡片空"的体验断裂：option.series.data 为空时
            // 用 Empty 占位组件替代 ReactECharts，避免用户看到一片白。
            const option = generateChartOption(chart);
            const ok = hasChartData(option);
            // 派生指标白盒：卡片标题下直接标出该指标的加工口径，不必跳血缘页也能看懂
            const dmHint = derivedMetricHint(chart);
            return (
              <Col xs={24} md={12} key={`chart-${index}`}>
                <Card
                  title={
                    <div>
                      <span>{chart.title}</span>
                      {dmHint ? (
                        <div style={{ marginTop: 2 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                            {dmHint}
                          </Typography.Text>
                        </div>
                      ) : null}
                    </div>
                  }
                  className="chart-card chart-card-clickable"
                  extra={<a onClick={(e) => { e.stopPropagation(); setDetailChart(chart); }}>查看详情</a>}
                  onClick={() => setDetailChart(chart)}
                >
                  {ok ? (
                    <ChartErrorBoundary title={chart.title}>
                      <ReactECharts option={sanitizeChartOption(option)} style={{ height: 300 }} notMerge={true} lazyUpdate={true} />
                    </ChartErrorBoundary>
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        chart.chart_type === 'scatter'
                          ? '该交叉维度需双方均为数值字段，已跳过绘制'
                          : '该图表无可绘制数据，请调整字段或更换图表类型'
                      }
                      style={{ height: 300, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
                    />
                  )}
                </Card>
              </Col>
            );
          })}
        </Row>
      </div>
    );
  };

  // 渲染明细表格
  const renderDetailTable = () => {
    if (!chartData || !chartData.data || chartData.data.length === 0) {
      return null;
    }

    const columns = chartData.columns.slice(0, 6).map((col: any) => ({
      title: col,
      dataIndex: col,
      key: col
    }));

    return (
      <div className="detail-layer">
        <h3 className="layer-title">数据明细</h3>
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <Card className="chart-card">
              <Table 
                columns={columns} 
                dataSource={chartData.data.slice(0, 5)} 
                size="small"
                pagination={{ pageSize: 5 }}
                scroll={{ x: 'max-content' }}
              />
            </Card>
          </Col>
        </Row>
      </div>
    );
  };

  // 渲染分析说明文本（L0 层，图表上方）
  // 按原型：标题为「AI 分析报告」，正文按段落（双换行）分段渲染，字号 14~16、行高 1.9。
  const renderAnalysisText = () => {
    if (!config || !config.analysis_text) return null;
    const paragraphs = String(config.analysis_text)
      .split(/\n{2,}/)
      .map((p: string) => p.trim())
      .filter(Boolean);
    return (
      <div className="analysis-text-layer">
        <div className="analysis-text-card">
          <div className="analysis-text-icon">
            <BulbOutlined />
          </div>
          <div className="analysis-text-content">
            <div className="analysis-text-title">AI 分析报告</div>
            <div className="analysis-text-body">
              {paragraphs.map((p: string, i: number) => (
                <p key={i} style={{ margin: i === 0 ? 0 : '12px 0 0' }}>{p}</p>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <Spin size="large" tip="加载看板..." />
      </div>
    );
  }

  if (!config) {
    // 修复"生成看板后页面跳空白"：原先是裸 Empty 无路可走。给出明确原因与出口
    // （常见于生成刚完成、后端配置尚未写入完成，刷新即可；或未带看板ID）
    return (
      <div style={{ minHeight: '70vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Empty description={urlId ? '看板不存在或仍在生成中' : '未指定看板ID'}>
          <Space direction="vertical" size={12} style={{ minWidth: 280 }}>
            <Space>
              {urlId && <Button type="primary" onClick={() => window.location.reload()}>刷新重试</Button>}
              <Button type={urlId ? 'default' : 'primary'} onClick={() => { window.location.href = '/upload' }}>返回数据上传</Button>
              <Button type="link" onClick={() => { window.location.href = '/dashboards' }}>查看历史看板</Button>
            </Space>
            {urlId && (
              <p style={{ color: '#999', fontSize: 12, margin: 0 }}>
                若刚生成完就看到此页，多为后台仍在写入看板配置，稍候刷新即可恢复
              </p>
            )}
          </Space>
        </Empty>
      </div>
    );
  }

  return (
    <div className={`dashboard-with-chat ${chatCollapsed ? 'chat-collapsed' : ''}`}>
      {/* 折叠时悬浮的"展开对话"按钮 */}
      {chatCollapsed && (
        <div className="chat-reopen-zone">
          <button
            className="chat-reopen-btn"
            onClick={() => setChatCollapsed(false)}
            title="展开数据对话，查看数据看板说明/提问"
          >
            <BulbOutlined className="reopen-icon" />
            <span className="reopen-text">数据助手</span>
          </button>
        </div>
      )}
      <div className="dashboard-main">
        {/* 看板头部：返回/标题/操作菜单 */}
        <DashboardOps
          id={urlId}
          title={title}
          onRename={setTitle}
          // onDelete 由 DashboardOps 内部在删除成功后跳转到 /dashboards；
          // 这里不再置空 config，避免跳转前闪屏"看板不存在"
          onDelete={() => {}}
        />

        {/* L1 KPI层 */}
        {renderKPILayer()}

        {/* L0 分析说明 */}
        {renderAnalysisText()}

        {/* L2 图表层 */}
        {renderChartLayer()}

        {/* L3 明细表 */}
        {renderDetailTable()}

        {/* 附录：A 字段字典 / B 清洗日志 / C 指标计算明细 / D 数据血缘（对齐方案B白盒交付） */}
        {urlId && <AppendixPanel dashboardId={urlId} />}
      </div>

      {/* 右侧对话面板 */}
      <div className="dashboard-chat-sidebar">
        <ChatPanel dashboardId={urlId} onAction={handleAction} onCollapse={() => setChatCollapsed(true)} />
      </div>

      {/* A03-02-01 图表详情子页：点击图表卡 → 大图 + 配置 + 数据明细 + 血缘链接 */}
      <Modal
        title={detailChart ? `${detailChart.title} · 图表详情` : ''}
        open={!!detailChart}
        onCancel={() => setDetailChart(null)}
        width={920}
        footer={[
          <Button key="lineage" onClick={() => { if (primaryDs) { navigate(`/lineage?dataset=${primaryDs}`); setDetailChart(null); } }}>
            查看数据血缘
          </Button>,
          <Button key="close" type="primary" onClick={() => setDetailChart(null)}>关闭</Button>,
        ]}
      >
        {detailChart && (
          <>
            {detailChart.chart_type !== 'kpi' && detailChart.chart_type !== 'table' ? (
              <ChartErrorBoundary title={detailChart.title}>
                <ReactECharts option={sanitizeChartOption(generateChartOption(detailChart))} style={{ height: 420 }} notMerge={true} lazyUpdate={true} />
              </ChartErrorBoundary>
            ) : (
              <Empty description={detailChart.chart_type === 'kpi' ? 'KPI 指标卡，无独立图表' : '明细表，无独立图表'} />
            )}

            <Descriptions title="图表配置" bordered column={1} size="small" style={{ marginTop: 16 }}>
              <Descriptions.Item label="标题">{detailChart.title}</Descriptions.Item>
              <Descriptions.Item label="类型">{detailChart.chart_type}</Descriptions.Item>
              <Descriptions.Item label="字段映射">
                X: {detailChart.x_field || '-'} ｜ Y: {detailChart.y_field || '-'} ｜ 分类: {detailChart.category_field || '-'} ｜ 值: {detailChart.value_field || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="配色">
                {detailChart.config?.color ? (
                  <span style={{ display: 'inline-flex', gap: 4 }}>
                    {String(detailChart.config.color).split(',').slice(0, 6).map((c: string, i: number) => (
                      <span key={i} style={{ width: 16, height: 16, borderRadius: 4, background: c.trim(), display: 'inline-block' }} />
                    ))}
                  </span>
                ) : '默认配色'}
              </Descriptions.Item>
            </Descriptions>

            {chartData?.data?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <p style={{ fontWeight: 600 }}>数据明细</p>
                <Table
                  columns={chartData.columns.slice(0, 6).map((col: any) => ({ title: col, dataIndex: col, key: col }))}
                  dataSource={chartData.data.slice(0, 20)}
                  size="small"
                  pagination={{ pageSize: 10 }}
                  scroll={{ x: 'max-content' }}
                />
              </div>
            )}
          </>
        )}
      </Modal>
    </div>
  );
};

export default DashboardPage;