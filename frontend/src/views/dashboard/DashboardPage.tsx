/**
 * M2-10 看板页 - 渲染真实AI生成的图表
 * L1 KPI卡 + L2趋势/分布/对比 + L3明细 + 右侧血缘问答
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Row, Col, Card, Statistic, Badge, Spin, Empty, Table, message, Typography, Breadcrumb } from 'antd';
import ReactECharts from 'echarts-for-react';
import { WarningOutlined, RiseOutlined, FallOutlined, ArrowLeftOutlined, BulbOutlined } from '@ant-design/icons';
import { http } from '../../utils/request';
import './DashboardPage.css';
import ChatPanel from '../../components/chat/ChatPanel';
import DashboardOps from './DashboardOps';

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
  if (fmt === 'currency') {
    const prefix = '¥';
    if (a >= 1e8) return { value: trimNum((val / 1e8).toFixed(2)) + '亿', prefix };
    if (a >= 1e4) return { value: trimNum((val / 1e4).toFixed(2)) + '万', prefix };
    return { value: Number.isInteger(val) ? val.toLocaleString() : val, prefix };
  }
  if (fmt === 'percent') return { value: val, suffix: '%' };
  if (a >= 1e8) return { value: trimNum((val / 1e8).toFixed(2)) + '亿' };
  if (a >= 1e7) return { value: trimNum((val / 1e4).toFixed(1)) + '万' };
  return { value: Number.isInteger(val) ? val.toLocaleString() : val };
}

const DashboardPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const urlId = searchParams.get('id') || '';
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [title, setTitle] = useState('看板');
  const [chartData, setChartData] = useState<any>(null);
  const [chatCollapsed, setChatCollapsed] = useState(false); // 折叠右侧对话，看板全屏

  // 处理AI动作（对话调整）
  const handleAction = useCallback((action: any) => {
    if (!config || !urlId) return;
    
    const { type, params } = action;
    let newConfig = JSON.parse(JSON.stringify(config));
    let changed = false;
    
    switch (type) {
      case 'change_chart': {
        // 修改图表类型
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
          charts[targetIdx].chart_type = params.target_type;
          changed = true;
          message.success(`已将图表改为${params.target_type}`);
        }
        break;
      }
      
      case 'add_chart': {
        // 新增图表
        const charts = newConfig.charts;
        const chartType = params.chart_type || 'bar';
        // 从已有图表推导真实字段：数值 y / 维度 x / 数据集ID，避免生成空图（x='category'/y='value' 不存在）
        let xf = '', yf = '', dsId = '';
        for (const c of charts) {
          if (!dsId) dsId = (c.dataset_id || c.datasetId || '');
          const y = c.y_field || c.value_field || '';
          const x = c.x_field || c.category_field || '';
          if (chartType === 'kpi' && y) { xf = x; yf = y; break; }
          if (!yf) yf = y;
          if (!xf) xf = x;
          if (yf && xf) break;
        }
        const newChart = {
          id: `chart_${charts.length + 1}`,
          chart_type: chartType,
          title: params.title || `新增${chartType}`,
          dataset_id: dsId || urlId,
          x_field: xf || undefined,
          y_field: yf || undefined,
          category_field: (params.category_field) || undefined,
          value_field: (params.value_field) || undefined,
          config: {},
        };
        charts.push(newChart);
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
    }
    
    if (changed) {
      setConfig(newConfig);
      // 保存到后端
      http.patch(`/dashboards/${urlId}`, { config: newConfig })
        .catch((err: any) => console.warn('保存配置到后端失败:', err));
    }
  }, [config, urlId]);
  
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
        // 3. 加载图表实际数据
        const dataRes = await http.get<any>(`/datasets/${primaryDs}/chart-data`);
        if (dataRes) {
          setChartData(dataRes);
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

  // 根据配置和真实数据生成ECharts option
  const generateChartOption = (chart: ChartConfig) => {
    if (!chartData || !chartData.data || chartData.data.length === 0) {
      return {
        title: { text: chart.title, left: 'center', textStyle: { fontSize: 14 } },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        series: [{ type: 'empty', label: { show: true, formatter: '暂无数据' } }]
      };
    }

    const { chart_type, title, x_field, y_field, category_field, value_field } = chart;
    const data = chartData.data;
    const numericStats = chartData.numeric_stats;

    switch (chart_type) {
      case 'kpi':
        // KPI 不在这里渲染，单独用KPICard
        return {};
      
      case 'line': {
        // 折线图：x=日期(按月份规约)，y=数值指标；若 y 为文本状态则计算"风险占比"或"计数量"
        const xF = x_field || '';
        const yF = y_field || '';
        const numFields = numericFieldSet(chartData);
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
        const categoryValues = [...new Set(data.map((r: any) => String(r[category_field || x_field || ''])))]
          .filter(v => v != null && v !== '');
        const valueMap = new Map();
        data.forEach((r: any) => {
          const cat = String(r[category_field || x_field || '']);
          const val = parseFloat(String(r[value_field || y_field || '']));
          if (!isNaN(val)) {
            valueMap.set(cat, (valueMap.get(cat) || 0) + val);
          }
        });
        const seriesData = Array.from(valueMap.entries()).map(([cat, val]) => ({ name: cat, value: val }));
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
        // 饼图：维度=解析出的真实分类列（避免落到数值列），值=每类计数（构成占比）
        const dim = resolveCategoricalDim(chart, chartData) || x_field || '';
        const cnt = new Map<string, number>();
        data.forEach((r: any) => {
          const v = String(r[dim] ?? '').trim() || '未知';
          cnt.set(v, (cnt.get(v) || 0) + 1);
        });
        const seriesData = Array.from(cnt.entries())
          .map(([name, value]) => ({ name, value }))
          .sort((a, b) => b.value - a.value)
          .slice(0, 8);

        return {
          title: { text: `${title}（按${dim}）`, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'item', formatter: '{b}: {c} 笔 ({d}%)' },
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
    const agg = c.aggregate || 'sum';
    let val: number;
    if (agg === 'max') val = Math.max(...nums);
    else if (agg === 'min') val = Math.min(...nums);
    else if (agg === 'mean' || agg === 'avg') val = nums.reduce((a: number, b: number) => a + b, 0) / nums.length;
    else val = nums.reduce((a: number, b: number) => a + b, 0);
    // 大金额紧凑格式化，避免卡片溢出显示不全
    const compact = formatCompact(val, c.format);
    return {
      value: compact.value,
      prefix: compact.prefix ?? (c.format === 'currency' ? '¥' : (c.prefix || '')),
      suffix: compact.suffix ?? (c.format === 'percent' ? '%' : (c.suffix || '')),
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
          {nonKpiCharts.map((chart: ChartConfig, index: number) => (
            <Col xs={24} md={12} key={`chart-${index}`}>
              <Card title={chart.title} className="chart-card">
                <ReactECharts option={generateChartOption(chart)} style={{ height: 300 }} />
              </Card>
            </Col>
          ))}
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
  const renderAnalysisText = () => {
    if (!config || !config.analysis_text) return null;
    return (
      <div className="analysis-text-layer">
        <div className="analysis-text-card">
          <div className="analysis-text-icon">
            <BulbOutlined />
          </div>
          <div className="analysis-text-content">
            <div className="analysis-text-title">AI 分析摘要</div>
            <div className="analysis-text-body">{config.analysis_text}</div>
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
    return <Empty description="看板不存在" />;
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
      </div>

      {/* 右侧对话面板 */}
      <div className="dashboard-chat-sidebar">
        <ChatPanel dashboardId={urlId} onAction={handleAction} onCollapse={() => setChatCollapsed(true)} />
      </div>
    </div>
  );
};

export default DashboardPage;