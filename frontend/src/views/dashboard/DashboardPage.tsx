/**
 * M2-10 看板页 - 渲染真实AI生成的图表
 * L1 KPI卡 + L2趋势/分布/对比 + L3明细 + 右侧血缘问答
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Row, Col, Card, Statistic, Badge, Spin, Empty, Table, message, Typography, Breadcrumb } from 'antd';
import ReactECharts from 'echarts-for-react';
import { WarningOutlined, RiseOutlined, FallOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { http } from '../../utils/request';
import './DashboardPage.css';
import ChatPanel from '../../components/chat/ChatPanel';
import DashboardOps from './DashboardOps';
import { API_BASE } from '../../utils/request';

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
            valueStyle={{fontSize: '28px', fontWeight: 'bold'}}
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
}

const API_ROOT = API_BASE;

const DashboardPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const urlId = searchParams.get('id') || '';
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [title, setTitle] = useState('看板');
  const [chartData, setChartData] = useState<any>(null);

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
        const newChart = {
          id: `chart_${charts.length + 1}`,
          chart_type: chartType,
          title: `新增${chartType}`,
          dataset_id: urlId,
          x_field: 'category',
          y_field: 'value',
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
      http.patch(`${API_ROOT}/dashboards/${urlId}`, { config: newConfig })
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
        const dashboardRes = await http.get<any>(`${API_ROOT}/dashboards/${urlId}`);
        if (dashboardRes?.name) {
          setTitle(dashboardRes.name);
        }
        if (dashboardRes?.config) {
          setConfig(dashboardRes.config);
        }
        
        // 2. 加载图表实际数据
        const dataRes = await http.get<any>(`${API_ROOT}/datasets/${dashboardRes.primary_dataset_id}/chart-data`);
        if (dataRes) {
          setChartData(dataRes);
        }
        
        message.success('看板加载完成');
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
        // 折线图：x_field = 日期，y_field = 数值
        const xValues = [...new Set(data.map((r: any) => r[x_field || '']))].filter(v => v != null && v !== '');
        const yData = data.map((r: any) => {
          const yVal = parseFloat(String(r[y_field || '']));
          return isNaN(yVal) ? null : yVal;
        }).filter((v: any) => v !== null);
        
        const xAxisData = xValues.slice(0, 50);
        const seriesData = yData.slice(0, 50);
        
        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'axis' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { 
            type: 'category', 
            data: xAxisData,
            boundaryGap: false
          },
          yAxis: { type: 'value', name: y_field },
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
        // 饼图：category_field = 分类，value_field = 数值
        const valueMap = new Map();
        data.forEach((r: any) => {
          const cat = String(r[category_field || '']);
          const val = parseFloat(String(r[value_field || '']));
          if (!isNaN(val) && val > 0) {
            valueMap.set(cat, (valueMap.get(cat) || 0) + val);
          }
        });
        const seriesData = Array.from(valueMap.entries())
          .map(([name, value]) => ({ name, value }))
          .sort((a, b) => b.value - a.value)
          .slice(0, 8); // 饼图不超过8块
        
        return {
          title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
          tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
          legend: { orient: 'vertical' as const, left: 'left', top: 'center' },
          series: [{
            type: 'pie',
            radius: ['40%', '70%'],
            data: seriesData,
            emphasis: {
              itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0, 0.5)' }
            },
            label: { formatter: '{b}: {d}%' }
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

  // 渲染KPI层
  const renderKPILayer = () => {
    if (!config) return null;
    const kpiCharts = config.charts.filter(c => c.chart_type === 'kpi');
    
    if (kpiCharts.length === 0) return null;

    return (
      <div className="kpi-layer">
        <Row gutter={[16, 16]}>
          {kpiCharts.map((chart, index) => (
            <Col xs={24} sm={12} md={6} key={`kpi-${index}`}>
              <KPICard
                title={chart.title}
                value={chart.config.value}
                prefix={chart.config.prefix}
                suffix={chart.config.suffix}
                change={chart.config.change}
                trend={chart.config.trend}
                warning={chart.config.warning}
                warningText={chart.config.warningText}
              />
            </Col>
          ))}
        </Row>
      </div>
    );
  };

  // 渲染图表层（非KPI）
  const renderChartLayer = () => {
    if (!config) return null;
    const nonKpiCharts = config.charts.filter(c => c.chart_type !== 'kpi' && c.chart_type !== 'table');
    
    if (nonKpiCharts.length === 0) return null;

    return (
      <div className="evidence-layer">
        <h3 className="layer-title">趋势与对比分析</h3>
        <Row gutter={[16, 16]}>
          {nonKpiCharts.map((chart, index) => (
            <Col xs={24} lg={index % 2 === 0 ? 12 : 12} key={`chart-${index}`}>
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
    <div className="dashboard-with-chat">
      <div className="dashboard-main">
        {/* 看板头部：返回/标题/操作菜单 */}
        <DashboardOps
          id={urlId}
          title={title}
          onRename={setTitle}
          onDelete={() => { setConfig(null); setTitle(''); }}
        />

        {/* L1 KPI层 */}
        {renderKPILayer()}
        
        {/* L2 图表层 */}
        {renderChartLayer()}
        
        {/* L3 明细表 */}
        {renderDetailTable()}
      </div>

      {/* 右侧对话面板 */}
      <div className="dashboard-chat-sidebar">
        <ChatPanel dashboardId={urlId} onAction={handleAction} />
      </div>
    </div>
  );
};

export default DashboardPage;