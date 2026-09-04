/**
 * 血缘中心 - M4-02
 * 层级图/超3层折叠/搜索高亮/详情面板4tab/影响范围高亮/一键验证动画/血缘问答
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { 
  Card, Input, Button, Tabs, Tag, Empty, Spin, 
  Tree, Badge, Tooltip, Drawer, List, Statistic, Row, Col,
  message, Segmented, Typography
} from 'antd';
import { 
  ArrowLeftOutlined, SearchOutlined, FileOutlined, DatabaseOutlined, 
  ToolOutlined, CalculatorOutlined, BarChartOutlined,
  CheckCircleOutlined, WarningOutlined, 
  QuestionCircleOutlined, SyncOutlined,
  ShareAltOutlined, InfoCircleOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
// 暴露到全局，兼容依赖 window.echarts 的第三方/调试获取实例
(window as any).echarts = echarts;
import './LineagePage.css';
import { http } from '../../utils/request';
import ChatPanel from '../../components/chat/ChatPanel';

const { TabPane } = Tabs;
const { Search } = Input;

// 血缘数据集 ID（列表页/详情页可在此切换查看不同数据集）
const LINEAGE_DATASET_ID = 'ds_001';

// 六层类型定义（对齐PRD原型）
const LAYER_TYPES = [
  { key: 'source', label: '原始数据层', icon: <FileOutlined />, color: '#1890ff' },
  { key: 'field', label: '字段标准化层', icon: <DatabaseOutlined />, color: '#52c41a' },
  { key: 'clean', label: '数据清洗层', icon: <ToolOutlined />, color: '#faad14' },
  { key: 'business', label: '业务加工层', icon: <CalculatorOutlined />, color: '#722ed1' },
  { key: 'agg', label: '聚合计算层', icon: <BarChartOutlined />, color: '#f5222d' },
  { key: 'chart', label: '看板输出层', icon: <BarChartOutlined />, color: '#eb2f96' }
];

// 节点类型
interface LineageNode {
  id: string;
  name: string;
  type: string;
  ref_id: string;
  description?: string;
  quality_flag?: string;
  x?: number;
  y?: number;
}

// 边类型
interface LineageEdge {
  id: string;
  source: string;
  target: string;
  transform_type: string;
  description?: string;
}

// 图谱数据
interface LineageGraph {
  dataset_id: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
  layers: Record<string, LineageNode[]>;
}

// 验证结果
interface VerifyResult {
  dataset_id: string;
  verified: boolean;
  error_count: number;
  existing_node_count: number;
  rebuilt_node_count: number;
}

// 影响分析
interface ImpactAnalysis {
  source_node: LineageNode;
  downstream_count: number;
  downstream_nodes: Array<{
    node_id: string;
    name: string;
    type: string;
    depth: number;
  }>;
}

const LineagePage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState<LineageGraph | null>(null);
  const [searchText, setSearchText] = useState('');
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [impactData, setImpactData] = useState<ImpactAnalysis | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [collapsedLayers, setCollapsedLayers] = useState<string[]>([]);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [chatPanelVisible, setChatPanelVisible] = useState(false);
  const [viewMode, setViewMode] = useState<'graph' | 'tree'>('graph');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  const chartRef = useRef<any>(null);
  // 延迟到布局完成后（双 RAF）再挂载图表，避免 container 宽度为 0 时 echarts.init 抛错
  const [chartReady, setChartReady] = useState(false);
  // 容器实际宽度，用于按层自适应横向排布，避免层被挤出可视区
  const [chartWidth, setChartWidth] = useState(720);

  // 加载血缘数据（真实后端 API）
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    http
      .get<LineageGraph>(`/lineage/graph/${LINEAGE_DATASET_ID}`)
      .then((data) => {
        if (!mounted) return;
        setGraphData(data);
      })
      .catch((err) => {
        if (!mounted) return;
        message.error(`加载血缘图谱失败: ${err?.message || '网络错误'}`);
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, []);

  // 数据就绪且进入图谱视图时，等两帧布局完成后再挂载 echarts
  useEffect(() => {
    if (loading || !graphData || graphData.nodes.length === 0 || viewMode !== 'graph') return;
    let r1: number, r2: number;
    const raf = window.requestAnimationFrame;
    r1 = raf(() => {
      r2 = raf(() => setChartReady(true));
    });
    return () => { window.cancelAnimationFrame(r1); window.cancelAnimationFrame(r2); };
  }, [loading, graphData, viewMode]);

  // 挂载后测量容器宽度（回调 ref 挂载即读 + ResizeObserver 响应缩放），用于自适应层间距
  const wrapRef = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const measure = () => {
      if (el.offsetWidth > 0) setChartWidth(el.offsetWidth);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    // ResizeObserver 不与组件卸载同步清理时的兜底
    (el as any).__roCleanup = () => ro.disconnect();
    return () => ro.disconnect();
  }, []);

  // 搜索高亮
  const handleSearch = (value: string) => {
    setSearchText(value);
    if (!value || !graphData) {
      setHighlightedNodes([]);
      return;
    }
    
    const matched = graphData.nodes
      .filter(n => n.name.toLowerCase().includes(value.toLowerCase()))
      .map(n => n.id);
    setHighlightedNodes(matched);
  };

  // 获取ECharts配置
  const getChartOption = useCallback(() => {
    if (!graphData) return {};
    
    const nodes = graphData.nodes.filter(n => {
      // 超3层折叠
      if (collapsedLayers.includes(n.type)) return false;
      return true;
    });
    
    const edges = graphData.edges.filter(e => {
      const sourceVisible = nodes.find(n => n.id === e.source);
      const targetVisible = nodes.find(n => n.id === e.target);
      return sourceVisible && targetVisible;
    });

    // 后端不返回坐标，按"层→列"自适应布局：每层一列，层内节点纵向排布
    const layerCount = Math.max(1, LAYER_TYPES.length);
    const spacing = Math.max(56, (chartWidth - 150) / Math.max(1, layerCount - 1));
    const pos = (n: LineageNode) => {
      const layerIdx = LAYER_TYPES.findIndex(l => l.key === n.type);
      const layerNodes = (graphData.layers[n.type] || []).map(l => l.id);
      const idx = layerNodes.indexOf(n.id);
      const count = Math.max(1, layerNodes.length);
      return {
        x: 60 + (layerIdx < 0 ? 0 : layerIdx) * spacing,
        y: 300 - (count - 1) * 45 + idx * 90,
      };
    };

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.dataType === 'node') {
            const node = graphData.nodes.find(n => n.id === params.data.id);
            return `${node?.name}<br/>类型: ${node?.type}<br/>${node?.description || ''}`;
          }
          return params.data.description || '';
        }
      },
      animationDurationUpdate: 1500,
      animationEasingUpdate: 'quinticInOut',
      series: [{
        type: 'graph',
        layout: 'none',
        symbolSize: 60,
        roam: true,
        label: {
          show: true,
          position: 'bottom',
          formatter: '{b}'
        },
        edgeSymbol: ['circle', 'arrow'],
        edgeSymbolSize: [4, 10],
        edgeLabel: {
          fontSize: 12
        },
        data: nodes.map(n => {
          const p = n.x !== undefined && n.x !== null ? n : { ...pos(n) };
          return {
            id: n.id,
            name: n.name,
            x: p.x,
            y: p.y,
            itemStyle: {
              color: LAYER_TYPES.find(l => l.key === n.type)?.color || '#999',
              borderColor: highlightedNodes.includes(n.id) ? '#ff4d4f' : 'transparent',
              borderWidth: highlightedNodes.includes(n.id) ? 3 : 0
            },
            symbol: n.type === 'chart' ? 'roundRect' : 'circle'
          };
        }),
        links: edges.map(e => ({
          source: e.source,
          target: e.target,
          description: e.description,
          lineStyle: {
            curveness: 0.2
          }
        })),
        lineStyle: {
          opacity: 0.9,
          width: 2,
          curveness: 0.2
        }
      }]
    };
  }, [graphData, highlightedNodes, collapsedLayers, chartWidth]);

  // 处理节点点击
  const handleNodeClick = (params: any) => {
    if (params.dataType === 'node' && graphData) {
      const node = graphData.nodes.find(n => n.id === params.data.id);
      if (node) {
        setSelectedNode(node);
        setDetailDrawerVisible(true);
        loadImpactAnalysis(node);
      }
    }
  };

  // 加载影响分析（真实后端 API）
  const loadImpactAnalysis = (node: LineageNode) => {
    setImpactData(null);
    http
      .get<ImpactAnalysis>(`/lineage/impact/${node.id}`)
      .then((data) => setImpactData(data))
      .catch((err) => message.warning(`影响分析加载失败: ${err?.message || '网络错误'}`));
  };

  // 一键验证（真实后端 API）
  const handleVerify = () => {
    setVerifying(true);
    http
      .post<VerifyResult>('/lineage/verify', { dataset_id: LINEAGE_DATASET_ID })
      .then((result) => {
        setVerifyResult(result);
        message.success(result.verified ? '血缘验证通过，误差=0' : `血缘验证完成，存在 ${result.error_count} 处误差`);
      })
      .catch((err) => message.error(`验证失败: ${err?.message || '网络错误'}`))
      .finally(() => setVerifying(false));
  };

  // 切换层折叠
  const toggleLayer = (layerKey: string) => {
    setCollapsedLayers(prev => 
      prev.includes(layerKey) 
        ? prev.filter(l => l !== layerKey)
        : [...prev, layerKey]
    );
  };

  // 树形结构数据
  const getTreeData = () => {
    if (!graphData) return [];
    
    return LAYER_TYPES.map(layer => ({
      title: layer.label,
      key: layer.key,
      icon: layer.icon,
      children: (graphData.layers[layer.key] || []).map(node => ({
        title: node.name,
        key: node.id,
        isLeaf: true
      }))
    }));
  };

  if (loading) {
    return (
      <div className="lineage-page-loading">
        <Spin size="large" tip="加载血缘图谱..." />
      </div>
    );
  }

  return (
    <div className="lineage-page">
      {/* 头部工具栏 */}
      <Card className="lineage-toolbar" size="small">
        <Row gutter={16} align="middle">
          <Col>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => {
                const from = searchParams.get('from')
                if (from) {
                  navigate(from)
                } else {
                  navigate(-1 as any)
                }
              }}
            >
              返回
            </Button>
          </Col>
          <Col flex="auto">
            <Search
              placeholder="搜索节点名称..."
              allowClear
              enterButton={<SearchOutlined />}
              onSearch={handleSearch}
              style={{ width: 300 }}
            />
          </Col>
          <Col>
            <Segmented
              options={[
                { label: '图谱视图', value: 'graph' },
                { label: '层级视图', value: 'tree' }
              ]}
              value={viewMode}
              onChange={(v) => setViewMode(v as 'graph' | 'tree')}
            />
          </Col>
          <Col>
            <Button 
              type="primary" 
              icon={<SyncOutlined spin={verifying} />}
              onClick={handleVerify}
              loading={verifying}
            >
              一键验证
            </Button>
          </Col>
          <Col>
            <Button 
              icon={<QuestionCircleOutlined />}
              type={chatPanelVisible ? 'primary' : 'default'}
              onClick={() => setChatPanelVisible(!chatPanelVisible)}
            >
              血缘问答
            </Button>
          </Col>
        </Row>
        
        {/* 层级筛选 */}
        <div className="layer-filters">
          {LAYER_TYPES.map(layer => (
            <Tag
              key={layer.key}
              color={collapsedLayers.includes(layer.key) ? 'default' : layer.color}
              icon={layer.icon}
              onClick={() => toggleLayer(layer.key)}
              className="layer-tag"
            >
              {layer.label}
              {collapsedLayers.includes(layer.key) && ' (已折叠)'}
            </Tag>
          ))}
        </div>
      </Card>

      {/* 验证结果 */}
      {verifyResult && (
        <Card className="verify-result-card" size="small">
          <Row gutter={24}>
            <Col>
              <Statistic
                title="验证状态"
                value={verifyResult.verified ? '通过' : '失败'}
                valueStyle={{ color: verifyResult.verified ? '#52c41a' : '#ff4d4f' }}
                prefix={verifyResult.verified ? <CheckCircleOutlined /> : <WarningOutlined />}
              />
            </Col>
            <Col>
              <Statistic title="误差数" value={verifyResult.error_count} />
            </Col>
            <Col>
              <Statistic title="现有节点" value={verifyResult.existing_node_count} />
            </Col>
            <Col>
              <Statistic title="重算节点" value={verifyResult.rebuilt_node_count} />
            </Col>
          </Row>
        </Card>
      )}

      {/* 主内容区 */}
      <div className={`lineage-main ${chatPanelVisible ? 'has-chat-panel' : ''}`}>
        <div className="lineage-content">
          {(!graphData || graphData.nodes.length === 0) ? (
            <Card className="lineage-graph-card">
              <Empty
                style={{ padding: '80px 0' }}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="当前数据集暂无血缘数据"
              >
                <span style={{ color: 'rgba(0,0,0,.45)' }}>上传数据并生成看板后，可在此查看文件→字段→清洗→口径→图表 六层血缘链路</span>
              </Empty>
            </Card>
          ) : viewMode === 'graph' ? (
            <Card className="lineage-graph-card">
              <div ref={wrapRef} style={{ width: '100%' }}>
              {chartReady && (
              <ReactECharts
                ref={chartRef}
                option={getChartOption()}
                style={{ width: '100%', height: 600 }}
                onChartReady={() => {
                  window.requestAnimationFrame(() => {
                    try {
                      const inst = chartRef.current?.getEchartsInstance();
                      inst?.resize();
                      inst?.setOption(getChartOption(), { notMerge: false });
                    } catch { /* 忽略 */ }
                  });
                }}
                onEvents={{
                  click: handleNodeClick
                }}
              />
              )}
              </div>
            </Card>
          ) : (
            <Card className="lineage-tree-card">
              <Tree
                treeData={getTreeData()}
                showIcon
                defaultExpandAll
                onSelect={(keys) => {
                  const nodeId = keys[0] as string;
                  const node = graphData?.nodes.find(n => n.id === nodeId);
                  if (node) {
                    setSelectedNode(node);
                    setDetailDrawerVisible(true);
                  }
                }}
              />
            </Card>
          )}
        </div>

        {/* 血缘问答右侧面板 — 复用统一 AI 助手样式（同一套标准） */}
        {chatPanelVisible && (
          <div className="lineage-chat-panel">
            <ChatPanel />
          </div>
        )}
      </div>

      {/* 详情抽屉 - 4 Tab */}
      <Drawer
        title={selectedNode?.name}
        placement="right"
        width={480}
        onClose={() => setDetailDrawerVisible(false)}
        open={detailDrawerVisible}
        className="node-detail-drawer"
      >
        {selectedNode && (
          <Tabs defaultActiveKey="basic">
            <TabPane tab="基本信息" key="basic">
              <List>
                <List.Item>
                  <List.Item.Meta
                    title="节点ID"
                    description={selectedNode.id}
                  />
                </List.Item>
                <List.Item>
                  <List.Item.Meta
                    title="节点类型"
                    description={LAYER_TYPES.find(l => l.key === selectedNode.type)?.label}
                  />
                </List.Item>
                <List.Item>
                  <List.Item.Meta
                    title="关联实体"
                    description={selectedNode.ref_id}
                  />
                </List.Item>
                <List.Item>
                  <List.Item.Meta
                    title="描述"
                    description={selectedNode.description || '暂无描述'}
                  />
                </List.Item>
                {selectedNode.quality_flag && (
                  <List.Item>
                    <List.Item.Meta
                      title="质量标记"
                      description={<Tag color="green">{selectedNode.quality_flag}</Tag>}
                    />
                  </List.Item>
                )}
              </List>
            </TabPane>
            
            <TabPane tab="上游血缘" key="upstream">
              <Empty description="上游节点列表" />
            </TabPane>
            
            <TabPane tab="下游影响" key="downstream">
              {impactData ? (
                <>
                  <div className="impact-summary">
                    <Badge count={impactData.downstream_count} showZero>
                      <span className="impact-label">下游节点数</span>
                    </Badge>
                  </div>
                  <List
                    dataSource={impactData.downstream_nodes}
                    renderItem={item => (
                      <List.Item>
                        <List.Item.Meta
                          title={item.name}
                          description={`${LAYER_TYPES.find(l => l.key === item.type)?.label} | 深度: ${item.depth}`}
                        />
                        <Tag color="blue">{item.type}</Tag>
                      </List.Item>
                    )}
                  />
                </>
              ) : (
                <Spin tip="加载影响分析..." />
              )}
            </TabPane>
            
            <TabPane tab="口径定义" key="definition">
              <Empty description="暂无口径定义">
                <Button type="primary">添加口径</Button>
              </Empty>
            </TabPane>
          </Tabs>
        )}
      </Drawer>

      {/* 血缘问答弹窗已改为右侧可折叠面板，删除以下代码 */}
    </div>
  );
};

export default LineagePage;
