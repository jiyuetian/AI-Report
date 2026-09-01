/**
 * 图表渲染器 - M2-11a/b/c/d (修复：使用 echarts-for-react 替代 @ant-design/charts)
 * line/bar/pie/scatter/table + 异常态处理
 */

import React from 'react';
import { Card, Empty, Spin, Badge, Tooltip, Table } from 'antd';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import { 
  WarningOutlined, 
  InfoCircleOutlined,
  FileTextOutlined,
  BarChartOutlined,
  PieChartOutlined,
  LineChartOutlined,
  DotChartOutlined
} from '@ant-design/icons';
import './ChartRenderer.css';

// 图表配置类型
export interface ChartConfig {
  chart_type: 'line' | 'bar' | 'pie' | 'scatter' | 'table' | 'kpi' | 'map' | 'heatmap';
  title: string;
  x_field?: string;
  y_field?: string;
  category_field?: string;
  value_field?: string;
  dataset_id: string;
  config?: Record<string, any>;
}

// 图表数据
export interface ChartData {
  data: Array<Record<string, any>>;
  total?: number;
  source_name?: string;
}

// 图表状态
export type ChartStatus = 'loading' | 'success' | 'error' | 'empty';

// 图表渲染器属性
interface ChartRendererProps {
  config: ChartConfig;
  data?: ChartData;
  status?: ChartStatus;
  errorMessage?: string;
  sourceName?: string;
  onDetail?: () => void;
  onEdit?: () => void;
}

// 图表图标映射
const CHART_ICONS = {
  line: <LineChartOutlined />,
  bar: <BarChartOutlined />,
  pie: <PieChartOutlined />,
  scatter: <DotChartOutlined />,
  table: <FileTextOutlined />,
  kpi: <BarChartOutlined />,
};

// Line图表
const LineChart: React.FC<{data: any[]; config: ChartConfig}> = ({data, config}) => {
  const option = {
    title: { text: config.title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { 
      type: 'category', 
      data: data.map(d => d[config.x_field || 'x']),
      boundaryGap: false
    },
    yAxis: { type: 'value' },
    series: [{
      data: data.map(d => d[config.y_field || 'y']),
      type: 'line',
      smooth: config.config?.smooth ?? true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: { width: 2 },
      itemStyle: { color: '#1890ff' }
    }]
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
};

// Bar图表
const BarChart: React.FC<{data: any[]; config: ChartConfig}> = ({data, config}) => {
  const isHorizontal = config.config?.horizontal ?? false;
  const option = {
    title: { text: config.title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: isHorizontal 
      ? { type: 'value' }
      : { type: 'category', data: data.map(d => d[config.x_field || 'x']) },
    yAxis: isHorizontal 
      ? { type: 'category', data: data.map(d => d[config.y_field || 'y']) }
      : { type: 'value' },
    series: [{
      data: data.map(d => d[config.y_field || config.x_field || 'y']),
      type: 'bar',
      itemStyle: { color: '#1890ff' },
      label: { show: true, position: 'top' }
    }]
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
};

// Pie图表
const PieChart: React.FC<{data: any[]; config: ChartConfig}> = ({data, config}) => {
  // 切片>8收敛到Top7+其他
  let processedData = data.map(d => ({
    name: d[config.category_field || 'category'],
    value: d[config.value_field || 'value']
  }));
  
  if (processedData.length > 8) {
    const sorted = [...processedData].sort((a, b) => b.value - a.value);
    const top7 = sorted.slice(0, 7);
    const others = sorted.slice(7);
    const othersSum = others.reduce((sum, item) => sum + item.value, 0);
    processedData = [...top7, { name: '其他', value: othersSum }];
  }
  
  const option = {
    title: { text: config.title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', left: 'left', top: 'center' },
    series: [{
      type: 'pie',
      radius: config.config?.donut ? ['40%', '70%'] : '70%',
      data: processedData,
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }
      },
      label: { formatter: '{b}: {d}%' }
    }]
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
};

// Scatter图表
const ScatterChart: React.FC<{data: any[]; config: ChartConfig}> = ({data, config}) => {
  const option = {
    title: { text: config.title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { 
      trigger: 'item',
      formatter: (params: any) => `${config.x_field}: ${params.data[0]}<br/>${config.y_field}: ${params.data[1]}`
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', name: config.x_field },
    yAxis: { type: 'value', name: config.y_field },
    series: [{
      type: 'scatter',
      data: data.map(d => [d[config.x_field || 'x'], d[config.y_field || 'y']]),
      symbolSize: 10,
      itemStyle: { color: '#1890ff' }
    }]
  };
  return <ReactECharts option={option} style={{ height: 300 }} />;
};

// Table图表
const TableChart: React.FC<{data: any[]; config: ChartConfig}> = ({data, config}) => {
  if (!data || data.length === 0) {
    return <Empty description="暂无数据" />;
  }
  
  // 自动生成列配置
  const columns = Object.keys(data[0]).map(key => ({
    title: key,
    dataIndex: key,
    key: key,
    sorter: (a: any, b: any) => {
      if (typeof a[key] === 'number') return a[key] - b[key];
      return String(a[key]).localeCompare(String(b[key]));
    },
  }));
  
  return (
    <Table
      dataSource={data.map((item, index) => ({ ...item, key: index }))}
      columns={columns}
      pagination={{
        pageSize: config.config?.page_size || 20,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 条`,
      }}
      scroll={{ x: 'max-content' }}
      size="small"
    />
  );
};

// 图表渲染器主组件
const ChartRenderer: React.FC<ChartRendererProps> = ({
  config,
  data,
  status = 'loading',
  errorMessage,
  sourceName,
  onDetail,
  onEdit,
}) => {
  // 渲染图表内容
  const renderChart = () => {
    if (!data || !data.data) {
      return <Empty description="暂无数据" />;
    }
    
    const chartData = data.data;
    
    switch (config.chart_type) {
      case 'line':
        return <LineChart data={chartData} config={config} />;
      case 'bar':
        return <BarChart data={chartData} config={config} />;
      case 'pie':
        return <PieChart data={chartData} config={config} />;
      case 'scatter':
        return <ScatterChart data={chartData} config={config} />;
      case 'table':
        return <TableChart data={chartData} config={config} />;
      default:
        return <Empty description={`暂不支持的图表类型: ${config.chart_type}`} />;
    }
  };

  // 渲染异常态
  const renderException = () => {
    switch (status) {
      case 'loading':
        return (
          <div className="chart-exception loading">
            <Spin size="large" tip="加载中..." />
          </div>
        );
      case 'error':
        return (
          <div className="chart-exception error">
            <WarningOutlined style={{ fontSize: 48, color: '#ff4d4f' }} />
            <p className="error-text">{errorMessage || '图表加载失败'}</p>
          </div>
        );
      case 'empty':
        return (
          <div className="chart-exception empty">
            <Empty description="暂无数据" />
          </div>
        );
      default:
        return null;
    }
  };

  // 卡片右上角操作
  const extra = (
    <div className="chart-actions">
      {sourceName && (
        <Tooltip title={`来源: ${sourceName}`}>
          <Badge 
            count={CHART_ICONS[config.chart_type as keyof typeof CHART_ICONS] || <BarChartOutlined />}
            style={{ backgroundColor: '#1890ff', marginRight: 8 }}
          />
          <span className="source-tag">{sourceName}</span>
        </Tooltip>
      )}
      {onDetail && (
        <Tooltip title="详情">
          <InfoCircleOutlined className="action-icon" onClick={onDetail} />
        </Tooltip>
      )}
    </div>
  );

  return (
    <Card 
      className={`chart-card chart-${config.chart_type}`}
      title={config.title}
      extra={extra}
      hoverable
    >
      <div className="chart-container">
        {status === 'success' ? renderChart() : renderException()}
      </div>
    </Card>
  );
};

export default ChartRenderer;