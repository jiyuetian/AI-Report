/**
 * 血缘中心 - M4-02（2026-09-18 按原型 index.html #s-lineage 重写）
 * 布局对齐原型：
 *   顶部工具条：追溯指标 chips + 搜索 + 展开/折叠中间层 + 影响范围分析
 *   横向六列链路：①数据源 → ②数据表 → ③字段 → ④清洗规则 → ⑤计算逻辑 → ⑥指标/图表
 *   右侧 330px 节点详情面板：节点详情 / 上游 N / 下游 N / 质量状态 四 Tab + 血缘问答
 *   底部：一键回溯验证（STEP1~4 逐层验证）
 * 保留图谱视图 / 层级视图作为补充视角。
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card, Input, Button, Tabs, Tag, Empty, Spin,
  Tree, Badge, Drawer, List, Row, Col,
  message, Segmented, Tooltip
} from 'antd';
import {
  ArrowLeftOutlined, SearchOutlined, FileOutlined, DatabaseOutlined,
  ToolOutlined, CalculatorOutlined, BarChartOutlined,
  CheckCircleOutlined, WarningOutlined,
  QuestionCircleOutlined, SyncOutlined, AimOutlined,
  NodeIndexOutlined, TableOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
// 暴露到全局，兼容依赖 window.echarts 的第三方/调试获取实例
(window as any).echarts = echarts;
import './LineagePage.css';
import { http } from '../../utils/request';
import ChatPanel from '../../components/chat/ChatPanel';
// Phase 5：SkillPanel 薄壳收口（展示本面板由哪些后端 skill 驱动，暗色自动继承）
import SkillPanel from '../../components/skills/SkillPanel';

// 血缘数据集 ID 兜底（正常情况下由 /lineage/resolve 动态解析）
const LINEAGE_DATASET_ID = 'ds_001';

// 血缘层级（对齐原型六列；business/agg 在链路视图合并为"⑤ 计算逻辑"一列）
const LAYER_TYPES = [
  { key: 'source', label: '① 数据源', icon: <FileOutlined />, color: '#1890ff' },
  { key: 'table', label: '② 数据表', icon: <TableOutlined />, color: '#13c2c2' },
  { key: 'field', label: '③ 字段', icon: <DatabaseOutlined />, color: '#52c41a' },
  { key: 'clean', label: '④ 清洗规则', icon: <ToolOutlined />, color: '#faad14' },
  { key: 'business', label: '⑤ 计算逻辑·口径', icon: <CalculatorOutlined />, color: '#722ed1' },
  { key: 'agg', label: '⑤ 计算逻辑·聚合', icon: <CalculatorOutlined />, color: '#f5222d' },
  { key: 'chart', label: '⑥ 指标 / 图表', icon: <BarChartOutlined />, color: '#eb2f96' }
];

// 链路视图列定义（business + agg 合并为一列，对齐原型"⑤ 计算逻辑"）
const CHAIN_COLUMNS: Array<{ keys: string[]; label: string }> = [
  { keys: ['source'], label: '① 数据源' },
  { keys: ['table'], label: '② 数据表' },
  { keys: ['field'], label: '③ 字段' },
  { keys: ['clean'], label: '④ 清洗规则' },
  { keys: ['business', 'agg'], label: '⑤ 计算逻辑' },
  { keys: ['chart'], label: '⑥ 指标 / 图表' }
];
// "展开/折叠中间层"折叠的列（②③④）
const MIDDLE_KEYS = ['table', 'field', 'clean'];

// 节点类型
interface LineageNode {
  id: string;
  name: string;
  type: string;
  ref_id: string;
  description?: string;
  quality_flag?: string;
  logic_json?: any;
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

// 数值格式化：大数转 万/亿（对齐原型"¥86.4亿"口径）
const fmtNum = (v: any): string => {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(2)}万`;
  if (abs >= 1) return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  return n.toPrecision(3);
};

const LineagePage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState<LineageGraph | null>(null);
  const [searchText, setSearchText] = useState('');
  const [selectedNode, setSelectedNode] = useState<LineageNode | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [impactData, setImpactData] = useState<ImpactAnalysis | null>(null);
  const [impactMode, setImpactMode] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [collapsedLayers, setCollapsedLayers] = useState<string[]>([]);
  const [middleFolded, setMiddleFolded] = useState(false);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [chatPanelVisible, setChatPanelVisible] = useState(false);
  const [qaText, setQaText] = useState('');
  // 追踪指标：非空时仅显示该指标加工链路（2026-09-18 修复：此前漏声明导致页面运行时 ReferenceError）
  const [traceNodeId, setTraceNodeId] = useState<string | null>(null);
  // 默认「加工链路」视图：横向六列，逐层看加工过程（对齐原型）
  const [viewMode, setViewMode] = useState<'chain' | 'graph' | 'tree'>('chain');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const chartRef = useRef<any>(null);
  // 延迟到布局完成后（双 RAF）再挂载图表，避免 container 宽度为 0 时 echarts.init 抛错
  const [chartReady, setChartReady] = useState(false);
  const [chartWidth, setChartWidth] = useState(720);

  // 图谱视图高度：按最大层可见节点数动态伸展，避免节点挤压重叠（对齐 #2 美化诉求）
  const graphHeight = useMemo(() => {
    if (!graphData) return 520;
    const maxLayerNodes = Math.max(
      1,
      ...LAYER_TYPES.map(l => graphData.nodes.filter(n => n.type === l.key).length)
    );
    return Math.min(1200, Math.max(480, maxLayerNodes * 88 + 140));
  }, [graphData]);

  // 解析当前要看哪个数据集的血缘：URL 指定 > /lineage/resolve（最近有看板的数据集） > 兜底常量。
  // 2026-09-18：默认解析到"有看板"的数据集，保证⑥指标/图表层一定有内容。
  const resolveDatasetId = useCallback(async (): Promise<string> => {
    const fromUrl = searchParams.get('dataset_id') || searchParams.get('ds');
    if (fromUrl) return fromUrl;
    try {
      const r: any = await http.get<any>('/lineage/resolve');
      const payload = r?.data ?? r;
      if (payload?.dataset_id) return String(payload.dataset_id);
    } catch { /* resolve 失败走兜底 */ }
    try {
      const list = await http.get<any>('/datasets');
      const rows: any[] = Array.isArray(list) ? list : (list?.items || list?.data || []);
      if (rows.length) {
        const sorted = [...rows].sort((a, b) =>
          String(b?.created_at || b?.updated_at || '').localeCompare(String(a?.created_at || a?.updated_at || ''))
        );
        const id = sorted[0]?.id || sorted[0]?.dataset_id;
        if (id) return String(id);
      }
    } catch { /* 列表失败就走兜底 */ }
    return LINEAGE_DATASET_ID;
  }, [searchParams]);

  // 加载血缘数据（真实后端 API）
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setVerifyResult(null);
    setImpactMode(false);
    resolveDatasetId()
      .then(dsId => http.get<LineageGraph>(`/lineage/graph/${dsId}`))
      .then((data) => {
        if (!mounted) return;
        setGraphData(data);
        // 默认选中第一个指标/图表节点（对齐原型：详情面板默认展示追溯目标）
        const charts = data?.layers?.chart || data?.nodes.filter(n => n.type === 'chart') || [];
        setSelectedNode(charts[0] || data?.nodes?.[0] || null);
      })
      .catch((err) => {
        if (!mounted) return;
        message.error(`加载血缘图谱失败: ${err?.message || '网络错误'}`);
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [resolveDatasetId]);

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

  const wrapRef = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const measure = () => {
      if (el.offsetWidth > 0) setChartWidth(el.offsetWidth);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    (el as any).__roCleanup = () => ro.disconnect();
    return () => ro.disconnect();
  }, []);

  // ===== 链路关系（本地边表推导，秒回） =====
  const nodeById = useCallback((id: string) =>
    graphData?.nodes.find(n => n.id === id), [graphData]);

  const upstreamOf = useCallback((node: LineageNode | null): LineageNode[] => {
    if (!node || !graphData) return [];
    return (graphData.edges || [])
      .filter(e => e.target === node.id)
      .map(e => nodeById(e.source))
      .filter((n): n is LineageNode => !!n);
  }, [graphData, nodeById]);

  const downstreamOf = useCallback((node: LineageNode | null): LineageNode[] => {
    if (!node || !graphData) return [];
    return (graphData.edges || [])
      .filter(e => e.source === node.id)
      .map(e => nodeById(e.target))
      .filter((n): n is LineageNode => !!n);
  }, [graphData, nodeById]);

  // 深度下游（影响范围分析：BFS 全链路）
  const deepDownstreamOf = useCallback((node: LineageNode | null): LineageNode[] => {
    if (!node || !graphData) return [];
    const adj: Record<string, string[]> = {};
    (graphData.edges || []).forEach(e => {
      (adj[e.source] = adj[e.source] || []).push(e.target);
    });
    const visited = new Set<string>([node.id]);
    const queue = [node.id];
    const out: LineageNode[] = [];
    while (queue.length) {
      const cur = queue.shift() as string;
      for (const nxt of (adj[cur] || [])) {
        if (visited.has(nxt)) continue;
        visited.add(nxt);
        const n = nodeById(nxt);
        if (n) out.push(n);
        queue.push(nxt);
      }
    }
    return out;
  }, [graphData, nodeById]);

  // 深度上游（追踪模式：沿边表 BFS 逆流到源文件，拿到该指标加工链路的全部节点）
  const deepUpstreamOf = useCallback((node: LineageNode | null): LineageNode[] => {
    if (!node || !graphData) return [];
    const radj: Record<string, string[]> = {};
    (graphData.edges || []).forEach(e => {
      (radj[e.target] = radj[e.target] || []).push(e.source);
    });
    const visited = new Set<string>([node.id]);
    const queue = [node.id];
    const out: LineageNode[] = [];
    while (queue.length) {
      const cur = queue.shift() as string;
      for (const prev of (radj[cur] || [])) {
        if (visited.has(prev)) continue;
        visited.add(prev);
        const n = nodeById(prev);
        if (n) out.push(n);
        queue.push(prev);
      }
    }
    return out;
  }, [graphData, nodeById]);

  // 追踪集合（2026-09-18 重写，修复"追踪指标后前几层仍显示全量节点"）：
  // 此前对被追踪指标做全量 BFS 上游——但后端把所有清洗节点/字段都连到每个业务节点，
  // BFS 会把 ①②③④ 层全部拉进来，等于没过滤。改为按层精确剪枝：
  //   ⑥ 只留被追踪指标；⑤ 沿边收它的 agg/business 加工节点；
  //   ③ 字段 = 加工节点的 components / field 成分字段（含从公式 expression 提取）；
  //   ④ 清洗 = 作用于这些字段的规则；①② 表/源为共享底座，全部保留。
  const traceSet = useMemo(() => {
    if (!traceNodeId || !graphData) return null;
    const tn = nodeById(traceNodeId);
    if (!tn) return null;
    const s = new Set<string>([tn.id]);

    // ⑤ 加工节点：沿边上游，仅收 agg/business
    const calcNodes: LineageNode[] = [];
    if (tn.type === 'agg' || tn.type === 'business') calcNodes.push(tn);
    const queue = [tn.id];
    const visited = new Set<string>([tn.id]);
    while (queue.length) {
      const cur = queue.shift() as string;
      for (const e of graphData.edges) {
        if (e.target !== cur || visited.has(e.source)) continue;
        visited.add(e.source);
        const n = nodeById(e.source);
        if (!n) continue;
        if (n.type === 'agg' || n.type === 'business') {
          calcNodes.push(n);
          s.add(n.id);
          queue.push(n.id);
        }
      }
    }

    // ③ 成分字段 + ④ 相关清洗规则
    const fieldNames = new Set<string>();
    calcNodes.forEach(c => {
      const lj = c.logic_json || {};
      (lj.components || []).forEach((f: string) => fieldNames.add(f));
      if (lj.field) fieldNames.add(lj.field);
      if (lj.expression) {
        (graphData.layers?.field || []).forEach(f => {
          if (f.name && String(lj.expression).includes(f.name)) fieldNames.add(f.name);
        });
      }
    });
    (graphData.layers?.field || []).forEach(f => {
      if (fieldNames.has(f.name)) s.add(f.id);
    });
    (graphData.layers?.clean || []).forEach(c => {
      const cf = c.logic_json?.field || '';
      const desc = c.description || '';
      if ((cf && fieldNames.has(cf)) || [...fieldNames].some(f => f && desc.includes(f))) {
        s.add(c.id);
      }
    });
    // ①② 表/源：共享底座全部保留
    [...(graphData.layers?.table || []), ...(graphData.layers?.source || [])].forEach(n => s.add(n.id));
    return s;
  }, [traceNodeId, graphData, nodeById]);

  // 追溯指标 chip 点击：开启/切换追踪；再点同一个 chip 退出追踪
  const toggleTrace = (node: LineageNode) => {
    setSelectedNode(node);
    if (traceNodeId === node.id) {
      setTraceNodeId(null);
    } else {
      setTraceNodeId(node.id);
    }
  };
  const metricChips = useCallback((): Array<{ node: LineageNode; label: string }> => {
    if (!graphData) return [];
    const chartNodes = graphData.layers?.chart || graphData.nodes.filter(n => n.type === 'chart') || [];
    const bizNodes = graphData.layers?.business || graphData.nodes.filter(n => n.type === 'business') || [];
    const chips: Array<{ node: LineageNode; label: string }> = [];
    chartNodes
      .slice()
      .sort((a, b) => (a.type === 'kpi' ? -1 : 0) - (b.type === 'kpi' ? -1 : 0))
      .forEach(c => {
        const v = c.logic_json?.current_value;
        chips.push({ node: c, label: v !== null && v !== undefined && v !== '' ? `${c.name} ${fmtNum(v)}` : c.name });
      });
    bizNodes.filter(b => (b.name || '').startsWith('派生指标')).forEach(b => {
      chips.push({ node: b, label: b.name.replace('派生指标: ', '') });
    });
    return chips.slice(0, 5);
  }, [graphData]);

  // 搜索高亮（对齐原型：搜节点名，命中红框并选中第一个）
  const handleSearch = (value: string) => {
    setSearchText(value);
    if (!value || !graphData) {
      setHighlightedNodes([]);
      return;
    }
    const matched = graphData.nodes
      .filter(n => n.name.toLowerCase().includes(value.toLowerCase()) || (n.description || '').includes(value))
      .map(n => n.id);
    setHighlightedNodes(matched);
    if (matched.length) {
      const first = nodeById(matched[0]);
      if (first) setSelectedNode(first);
    }
  };

  // 点击节点：链路视图 → 右侧面板；图谱/层级视图 → 抽屉
  const selectNode = (node: LineageNode, openDrawer = false) => {
    setSelectedNode(node);
    if (openDrawer) {
      setDetailDrawerVisible(true);
      loadImpactAnalysis(node);
    }
  };

  // 获取ECharts配置（图谱视图）
  const getChartOption = useCallback(() => {
    if (!graphData) return {};

    const nodes = graphData.nodes.filter(n => {
      if (collapsedLayers.includes(n.type)) return false;
      // 追踪模式：只保留该指标加工链路上的节点
      if (traceSet && !traceSet.has(n.id)) return false;
      return true;
    });

    const edges = graphData.edges.filter(e => {
      const sourceVisible = nodes.find(n => n.id === e.source);
      const targetVisible = nodes.find(n => n.id === e.target);
      return sourceVisible && targetVisible;
    });

    // 2026-09-18 布局重写（修复节点重叠）：
    // ① 不再信任后端存的 x/y（旧数据常把同层节点挤在同一坐标）→ 每次按层重排；
    // ② 行距按"节点最多的层"撑开，节点再多也互不压盖；
    // ③ 图表高度随最大层数动态伸展（此前固定 600px，十几条清洗规则必然叠成一坨）；
    // ④ 标签截断 + hideOverlap，长字段名不再糊成一团。
    const layerIdxOf = (t: string) => LAYER_TYPES.findIndex(l => l.key === t);
    const byLayer: Record<string, LineageNode[]> = {};
    nodes.forEach(n => { (byLayer[n.type] = byLayer[n.type] || []).push(n); });
    const maxCount = Math.max(1, ...Object.values(byLayer).map(a => a.length));
    const rowGap = 84;
    const colGap = Math.max(150, (chartWidth - 180) / Math.max(1, LAYER_TYPES.length - 1));
    const posOf = (n: LineageNode) => {
      const li = Math.max(0, layerIdxOf(n.type));
      const arr = byLayer[n.type] || [n];
      const idx = arr.findIndex(x => x.id === n.id);
      const count = Math.max(1, arr.length);
      return { x: 80 + li * colGap, y: (idx - (count - 1) / 2) * rowGap };
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
      animationDurationUpdate: 800,
      animationEasingUpdate: 'quinticInOut',
      labelLayout: { hideOverlap: true },
      series: [{
        type: 'graph',
        layout: 'none',
        roam: true,
        label: {
          show: true, position: 'bottom', distance: 6,
          fontSize: 11, width: 110, overflow: 'truncate',
          formatter: '{b}', color: '#595959'
        },
        edgeSymbol: ['circle', 'arrow'],
        edgeSymbolSize: [4, 9],
        edgeLabel: { fontSize: 11 },
        data: nodes.map(n => {
          const p = posOf(n);
          return {
            id: n.id,
            name: n.name,
            x: p.x,
            y: p.y,
            // 指标/图表节点用圆角矩形强调；其余统一小圆，行距>符号尺寸保证不重叠
            symbolSize: n.type === 'chart' ? [110, 44] : 46,
            itemStyle: {
              color: LAYER_TYPES.find(l => l.key === n.type)?.color || '#999',
              borderColor: highlightedNodes.includes(n.id) || impactMode && deepDownstreamOf(selectedNode).some(d => d.id === n.id)
                ? '#ff4d4f' : 'rgba(255,255,255,.65)',
              borderWidth: highlightedNodes.includes(n.id) || (impactMode && deepDownstreamOf(selectedNode).some(d => d.id === n.id)) ? 3 : 1
            },
            symbol: n.type === 'chart' ? 'roundRect' : 'circle'
          };
        }),
        links: edges.map(e => ({
          source: e.source,
          target: e.target,
          description: e.description,
          lineStyle: { curveness: 0.15 }
        })),
        lineStyle: { opacity: 0.55, width: 1.5, curveness: 0.15, color: '#bfbfbf' }
      }]
    };
  }, [graphData, highlightedNodes, collapsedLayers, chartWidth, impactMode, selectedNode, deepDownstreamOf]);

  // 加载影响分析（真实后端 API）
  const loadImpactAnalysis = (node: LineageNode) => {
    setImpactData(null);
    http
      .get<ImpactAnalysis>(`/lineage/impact/${node.id}`)
      .then((data) => setImpactData(data))
      .catch((err) => message.warning(`影响分析加载失败: ${err?.message || '网络错误'}`));
  };

  // 一键回溯验证（对齐原型底部验证卡：POST /lineage/verify 重算比对）
  const handleVerify = () => {
    setVerifying(true);
    http
      .post<VerifyResult>('/lineage/verify', { dataset_id: graphData?.dataset_id || LINEAGE_DATASET_ID })
      .then((result) => {
        setVerifyResult(result);
        message.success(result.verified ? '回溯验证通过：四层链路重算与看板显示一致' : `验证完成，存在 ${result.error_count} 处差异`);
      })
      .catch((err) => message.error(`验证失败: ${err?.message || '网络错误'}`))
      .finally(() => setVerifying(false));
  };

  // 切换层折叠（层标签）
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

  // ===== 验证链 STEP 数据（对齐原型 STEP1~4）=====
  const buildVerifySteps = () => {
    if (!graphData) return [];
    const target = selectedNode?.type === 'chart'
      ? selectedNode
      : (graphData.layers?.chart || [])[0] || null;
    const step1 = target
      ? { title: 'STEP 1 · 指标值', main: `${target.name}${target.logic_json?.current_value != null ? ` ${fmtNum(target.logic_json.current_value)}` : ''}`, sub: '看板图表显示值' }
      : { title: 'STEP 1 · 指标值', main: '—', sub: '暂无图表输出' };
    const ups = upstreamOf(target);
    const calcNode = ups.find(u => u.type === 'agg' || u.type === 'business');
    const step2 = calcNode
      ? { title: 'STEP 2 · 计算口径', main: calcNode.name.replace(/^聚合: /, ''), sub: calcNode.description || '加工口径' }
      : { title: 'STEP 2 · 计算口径', main: '—', sub: '暂无加工口径记录' };
    const cleans = graphData.layers?.clean || [];
    const step3 = {
      title: 'STEP 3 · 清洗影响',
      main: cleans.length ? `${cleans.length} 条规则` : '+0 行',
      sub: cleans.length ? '全部动作已写入清洗层，可追溯可撤销' : '本数据集未执行清洗'
    };
    const src = (graphData.layers?.source || [])[0];
    const stg = (graphData.layers?.table || [])[0];
    const step4 = {
      title: 'STEP 4 · 原始行定位',
      main: src ? src.name : '—',
      sub: stg ? stg.description : (src ? src.description : '原始文件')
    };
    return [step1, step2, step3, step4];
  };

  if (loading) {
    return (
      <div className="lineage-page-loading">
        <Spin size="large" tip="加载血缘图谱..." />
      </div>
    );
  }

  const chips = metricChips();
  const impactSet = impactMode && selectedNode ? new Set(deepDownstreamOf(selectedNode).map(n => n.id)) : new Set<string>();
  const isNodeHighlighted = (id: string) =>
    highlightedNodes.includes(id) || (impactMode && impactSet.has(id));

  // ===== 链路视图节点卡（对齐原型 .lnode）=====
  const renderLNode = (n: LineageNode) => {
    const selected = selectedNode?.id === n.id;
    const hl = isNodeHighlighted(n.id);
    const flag = n.quality_flag || '';
    return (
      <div
        key={n.id}
        className={`lnode${selected ? ' selected' : ''}${hl ? ' highlighted' : ''}`}
        onClick={() => selectNode(n)}
      >
        <div className="ln-name" title={n.name}>
          {n.type === 'chart' && <span style={{ marginRight: 4 }}>🎯</span>}
          {n.name}
        </div>
        <div className="ln-sub" title={n.description || ''}>
          {n.description || '—'}
        </div>
        {flag && (
          <div className="ln-flag">
            {flag.includes('⚠') ? (
              <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>{flag}</Tag>
            ) : flag.includes('*') ? (
              <Tag color="gold" style={{ margin: 0, fontSize: 11 }}>{flag}</Tag>
            ) : (
              <Tag color="green" style={{ margin: 0, fontSize: 11 }}>{flag}</Tag>
            )}
          </div>
        )}
      </div>
    );
  };

  // ===== 链路视图（横向六列）=====
  const renderChain = () => {
    if (!graphData || graphData.nodes.length === 0) return null;
    const cols = middleFolded
      ? CHAIN_COLUMNS.filter(c => !c.keys.some(k => MIDDLE_KEYS.includes(k)))
      : CHAIN_COLUMNS;
    return (
      <Card className="lineage-graph-card chain-card">
        <div className="chain-scroll">
          {cols.map((col, ci) => {
            const isMiddleGapCol = middleFolded && ci === 1;
            const layerNodes = col.keys
              .flatMap(k => collapsedLayers.includes(k) ? [] : (graphData.layers[k] || graphData.nodes.filter(n => n.type === k) || []))
              // 追踪模式：只保留该指标加工链路上的节点，无关指标全部隐藏
              .filter(n => !traceSet || traceSet.has(n.id));
            return (
              <React.Fragment key={col.label}>
                {ci > 0 && <div className="chain-arrow">→</div>}
                {isMiddleGapCol && (
                  <div className="lineage-layer">
                    <div className="chain-col-title">② 中间层</div>
                    <div className="lnode lnode-folded" onClick={() => setMiddleFolded(false)}>
                      <div className="ln-name">⇢ 3 个中间层已折叠</div>
                      <div className="ln-sub">数据表 → 字段 → 清洗规则（点击展开）</div>
                    </div>
                  </div>
                )}
                {!isMiddleGapCol && (
                  <div className="lineage-layer">
                    <div className="chain-col-title">{col.label}</div>
                    {layerNodes.length === 0 ? (
                      <div className="lnode lnode-empty">该层暂无处理记录</div>
                    ) : (
                      layerNodes.map(renderLNode)
                    )}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
        <div className="chain-tip">
          {traceSet
            ? <>🔎 追踪中：仅显示所选指标的加工链路（无关指标已隐藏）· 点击顶部蓝色标签或再点该指标可退出</>
            : <>💡 点击任意节点查看右侧详情 · 点击顶部「追溯指标」可只看该指标加工链路 · ✓ 质检通过 · ⚠ 有遗留问题 · * 含估算值</>}
        </div>
      </Card>
    );
  };

  // ===== 右侧详情面板（对齐原型 330px 四 Tab 面板）=====
  // 2026-09-18：对齐原型"加工板块"——选中指标节点时，计算口径自动取其上游 agg/business 节点的
  // 加工公式（此前只显示节点自身 description，指标节点常为空，导致"要点开清洗/逻辑节点才能看到公式"）。
  const calcFormulaOf = (node: LineageNode | null): { formula: string; source: string } => {
    if (!node) return { formula: '', source: '' };
    if (node.type === 'agg' || node.type === 'business') {
      return { formula: node.description || node.name.replace(/^聚合: /, ''), source: node.name };
    }
    const ups = upstreamOf(node);
    const calc = ups.find(u => u.type === 'agg' || u.type === 'business');
    if (calc) {
      return { formula: calc.description || calc.name.replace(/^聚合: /, ''), source: calc.name };
    }
    return { formula: node.description || '', source: '' };
  };

  const renderDetailPanel = () => {
    const node = selectedNode;
    const ups = upstreamOf(node);
    const downs = downstreamOf(node);
    const layerLabel = LAYER_TYPES.find(l => l.key === node?.type)?.label || '';
    const calcInfo = calcFormulaOf(node);
    return (
      <div className="lineage-detail-panel">
        <Card size="small" className="detail-panel-card">
          <Tabs
            defaultActiveKey="basic"
            size="small"
            items={[
              {
                key: 'basic',
                label: '节点详情',
                children: node ? (
                  <div>
                    <div className="detail-head">
                      <b className="detail-title">{node.name}</b>
                      {node.quality_flag ? (
                        <Tag color={node.quality_flag.includes('⚠') ? 'orange' : node.quality_flag.includes('*') ? 'gold' : 'green'}>
                          {node.quality_flag}
                        </Tag>
                      ) : (
                        <Tag color="green">质检通过</Tag>
                      )}
                    </div>
                    <table className="detail-table">
                      <tbody>
                        <tr>
                          <td className="dt-key">节点层级</td>
                          <td>{layerLabel}</td>
                        </tr>
                        <tr>
                          <td className="dt-key">当前值</td>
                          <td className="fw600">
                            {node.logic_json?.current_value != null && node.logic_json.current_value !== ''
                              ? `${fmtNum(node.logic_json.current_value)}${node.logic_json?.period ? `（${node.logic_json.period}）` : ''}`
                              : (node.type === 'chart' ? '见看板' : '—')}
                          </td>
                        </tr>
                        <tr>
                          <td className="dt-key">计算口径</td>
                          <td className="fs12">
                            {calcInfo.formula
                              ? <>
                                <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{calcInfo.formula}</div>
                                {calcInfo.source && (
                                  <div style={{ color: '#8c8c8c', marginTop: 2 }}>口径来源：{calcInfo.source}</div>
                                )}
                              </>
                              : '—'}
                          </td>
                        </tr>
                        <tr>
                          <td className="dt-key">上游</td>
                          <td className="fs12">
                            {ups.length ? ups.map(u => u.name).join('、') : '—'}
                          </td>
                        </tr>
                        <tr>
                          <td className="dt-key">下游</td>
                          <td className="fs12">
                            {downs.length ? downs.map(d => d.name).join('、') : '—'}
                          </td>
                        </tr>
                        {(node.description || '').match(/估算|填充|推断/) && (
                          <tr>
                            <td className="dt-key">估算依赖</td>
                            <td className="fs12" style={{ color: '#d48806' }}>
                              含估算值：结论方向可信，绝对值存在误差带，建议看板标注 *
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                    <div className="qa-alert">
                      💬 血缘问答：在下方输入框继续追问该指标的来源与加工逻辑，AI 会结合本条链路作答。
                    </div>
                    <div className="qa-row">
                      <Input
                        size="small"
                        placeholder="继续追问指标来源…"
                        value={qaText}
                        onChange={e => setQaText(e.target.value)}
                        onPressEnter={() => { if (qaText.trim()) { setChatPanelVisible(true); setQaText(''); } }}
                      />
                      <Button
                        type="primary"
                        size="small"
                        onClick={() => { if (qaText.trim()) { setChatPanelVisible(true); setQaText(''); } else { setChatPanelVisible(true); } }}
                      >
                        问
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击左侧任意节点查看详情" />
                )
              },
              {
                key: 'upstream',
                label: `上游 ${ups.length}`,
                children: ups.length ? (
                  <List
                    size="small"
                    dataSource={ups}
                    renderItem={u => (
                      <List.Item style={{ cursor: 'pointer' }} onClick={() => selectNode(u)}>
                        <List.Item.Meta
                          title={u.name}
                          description={LAYER_TYPES.find(l => l.key === u.type)?.label}
                        />
                      </List.Item>
                    )}
                  />
                ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无上游节点（链路起点）" />
              },
              {
                key: 'downstream',
                label: `下游 ${downs.length}`,
                children: downs.length ? (
                  <List
                    size="small"
                    dataSource={downs}
                    renderItem={d => (
                      <List.Item style={{ cursor: 'pointer' }} onClick={() => selectNode(d)}>
                        <List.Item.Meta
                          title={d.name}
                          description={LAYER_TYPES.find(l => l.key === d.type)?.label}
                        />
                      </List.Item>
                    )}
                  />
                ) : (
                  <div>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无直接下游" />
                    <div className="fs12" style={{ color: '#8c8c8c', textAlign: 'center' }}>
                      该节点为链路终点（看板输出）
                    </div>
                  </div>
                )
              },
              {
                key: 'quality',
                label: '质量状态',
                children: (
                  <div>
                    <div style={{ marginBottom: 12 }}>
                      {node?.quality_flag ? (
                        <Tag color={node.quality_flag.includes('⚠') ? 'orange' : node.quality_flag.includes('*') ? 'gold' : 'green'}>
                          {node.quality_flag.includes('⚠') ? <WarningOutlined /> : <CheckCircleOutlined />} {node.quality_flag}
                        </Tag>
                      ) : (
                        <Tag color="green"><CheckCircleOutlined /> 质检通过</Tag>
                      )}
                    </div>
                    <div className="fs12" style={{ color: '#595959' }}>
                      {node?.quality_flag?.includes('⚠')
                        ? '该节点存在未处理的质检遗留问题，可回到质检页逐条处理后重新生成看板。'
                        : node?.quality_flag?.includes('*')
                          ? '该节点依赖估算值填充，绝对值存在误差带；结论方向仍可信。'
                          : '该节点无遗留质量问题。'}
                    </div>
                  </div>
                )
              }
            ]}
          />
        </Card>
      </div>
    );
  };

  // ===== 底部一键回溯验证（对齐原型 STEP1~4 + 结果告警）=====
  const renderVerifyCard = () => {
    const steps = buildVerifySteps();
    const target = selectedNode?.type === 'chart'
      ? selectedNode
      : (graphData?.layers?.chart || [])[0];
    return (
      <Card size="small" className="verify-card">
        <div className="verify-head">
          <span className="verify-title">🔎 一键回溯验证{target ? ` · ${target.name}` : ''}</span>
          <Button type="primary" size="small" icon={<SyncOutlined spin={verifying} />} loading={verifying} onClick={handleVerify}>
            开始逐层验证
          </Button>
        </div>
        <div className="verify-steps">
          {steps.map((s, i) => (
            <React.Fragment key={s.title}>
              {i > 0 && <div className="chain-arrow">→</div>}
              <div className="verify-step">
                <div className="vs-title">{s.title}</div>
                <div className="vs-main">{s.main}</div>
                <div className="vs-sub">{s.sub}</div>
              </div>
            </React.Fragment>
          ))}
        </div>
        {verifyResult && (
          <div className={`verify-outcome ${verifyResult.verified ? 'ok' : 'warn'}`}>
            {verifyResult.verified ? '✅' : '⚠️'}{' '}
            <b>{verifyResult.verified ? '验证通过：' : '验证存在差异：'}</b>
            {verifyResult.verified
              ? `链路重算与现有血缘一致（${verifyResult.existing_node_count} 节点），验证记录已存档，可供审计复查。`
              : `发现 ${verifyResult.error_count} 处差异（现有 ${verifyResult.existing_node_count} 节点 / 重算 ${verifyResult.rebuilt_node_count} 节点），建议重新生成看板以刷新血缘。`}
          </div>
        )}
      </Card>
    );
  };

  return (
    <SkillPanel panelKind="lineage" title="数据血缘">
    <div className="lineage-page">
      {/* 页头 */}
      <div className="lineage-page-head">
        <div className="lph-title-row">
          <Button
            type="text"
            size="small"
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              // 2026-09-18 修复：从看板页带 dashboard_id 进来时，返回必须回到该看板，
              // 而不是裸 /dashboard（那会命中"未指定看板ID"空页）
              const dashId = searchParams.get('dashboard_id');
              if (dashId) {
                navigate(`/dashboard?id=${dashId}`);
                return;
              }
              const from = searchParams.get('from')
              if (from) navigate(from)
              else navigate(-1 as any)
            }}
          >
            返回
          </Button>
          <h2 className="lph-title">数据血缘中心</h2>
        </div>
        <div className="lph-desc">每个数字都可回溯：从看板指标一路反查到原始 Excel 行，验证分析结论可信</div>
      </div>

      {/* 工具条：追溯指标 chips + 搜索 + 折叠 + 影响分析 */}
      <Card className="lineage-toolbar" size="small">
        <div className="toolbar-row">
          <span className="tb-label">追溯指标：</span>
          <div className="metric-chips">
            {chips.length === 0 && <span className="fs12" style={{ color: '#8c8c8c' }}>生成看板后这里会出现可追溯指标</span>}
            {chips.map(({ node, label }) => (
              <span
                key={node.id}
                className={`metric-chip${traceNodeId === node.id ? ' active' : ''}`}
                title={traceNodeId === node.id ? '再次点击退出追踪' : '点击追踪该指标的加工链路'}
                onClick={() => toggleTrace(node)}
              >
                {label}
              </span>
            ))}
            {traceNodeId && nodeById(traceNodeId) && (
              <Tag
                color="blue"
                closable
                onClose={() => setTraceNodeId(null)}
                style={{ marginLeft: 4, cursor: 'pointer' }}
              >
                追踪中：仅显示「{nodeById(traceNodeId)!.name}」加工链路
              </Tag>
            )}
          </div>
          <div className="tb-spacer" />
          <Input
            size="small"
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索节点（如 抵押率）"
            onChange={e => handleSearch(e.target.value)}
            style={{ width: 200 }}
          />
          <Button size="small" onClick={() => setMiddleFolded(f => !f)} icon={<NodeIndexOutlined />}>
            {middleFolded ? '展开中间层' : '折叠中间层'}
          </Button>
          <Button
            size="small"
            icon={<AimOutlined />}
            type={impactMode ? 'primary' : 'default'}
            onClick={() => {
              if (!selectedNode) { message.info('请先点击一个节点，再分析它的影响范围'); return; }
              setImpactMode(m => !m);
              if (!impactMode) {
                const n = deepDownstreamOf(selectedNode).length;
                message.success(`影响范围分析：${selectedNode.name} 下游共影响 ${n} 个节点（红色高亮）`);
              }
            }}
          >
            影响范围分析
          </Button>
          <Tooltip title="AI 血缘问答">
            <Button
              size="small"
              icon={<QuestionCircleOutlined />}
              type={chatPanelVisible ? 'primary' : 'default'}
              onClick={() => setChatPanelVisible(!chatPanelVisible)}
            >
              问
            </Button>
          </Tooltip>
          <Segmented
            size="small"
            options={[
              { label: '加工链路', value: 'chain' },
              { label: '图谱视图', value: 'graph' },
              { label: '层级视图', value: 'tree' }
            ]}
            value={viewMode}
            onChange={(v) => setViewMode(v as 'chain' | 'graph' | 'tree')}
          />
        </div>

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
                <span style={{ color: 'rgba(0,0,0,.45)' }}>上传数据并生成看板后，可在此查看 文件→数据表→字段→清洗→计算逻辑→图表 六层血缘链路</span>
              </Empty>
            </Card>
          ) : viewMode === 'chain' ? (
            /* 加工链路：横向六列 + 右侧详情面板（对齐原型） */
            <div className="chain-layout">
              <div className="chain-left">{renderChain()}</div>
              {renderDetailPanel()}
            </div>
          ) : viewMode === 'graph' ? (
            <Card className="lineage-graph-card">
              <div ref={wrapRef} style={{ width: '100%' }}>
                {chartReady && (
                  <ReactECharts
                    ref={chartRef}
                    option={getChartOption()}
                    style={{ width: '100%', height: graphHeight }}
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
                      click: (params: any) => {
                        if (params.dataType === 'node' && graphData) {
                          const node = graphData.nodes.find(n => n.id === params.data.id);
                          if (node) selectNode(node, true);
                        }
                      }
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
                  if (node) selectNode(node, true);
                }}
              />
            </Card>
          )}

          {/* 底部一键回溯验证（链路视图显示） */}
          {viewMode === 'chain' && graphData && graphData.nodes.length > 0 && renderVerifyCard()}
        </div>

        {/* 血缘问答右侧面板 — 复用统一 AI 助手样式 */}
        {chatPanelVisible && (
          <div className="lineage-chat-panel">
            <ChatPanel onCollapse={() => setChatPanelVisible(false)} />
          </div>
        )}
      </div>

      {/* 详情抽屉（图谱/层级视图用） */}
      <Drawer
        title={selectedNode?.name}
        placement="right"
        width={480}
        onClose={() => setDetailDrawerVisible(false)}
        open={detailDrawerVisible}
        className="node-detail-drawer"
      >
        {selectedNode && (
          <Tabs defaultActiveKey="basic" items={[
            {
              key: 'basic',
              label: '基本信息',
              children: (
                <List>
                  <List.Item>
                    <List.Item.Meta title="节点ID" description={selectedNode.id} />
                  </List.Item>
                  <List.Item>
                    <List.Item.Meta
                      title="节点类型"
                      description={LAYER_TYPES.find(l => l.key === selectedNode.type)?.label}
                    />
                  </List.Item>
                  <List.Item>
                    <List.Item.Meta title="关联实体" description={selectedNode.ref_id} />
                  </List.Item>
                  <List.Item>
                    <List.Item.Meta title="描述" description={selectedNode.description || '暂无描述'} />
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
              )
            },
            {
              key: 'upstream',
              label: '上游血缘',
              children: upstreamOf(selectedNode).length ? (
                <List
                  size="small"
                  dataSource={upstreamOf(selectedNode)}
                  renderItem={u => (
                    <List.Item>
                      <List.Item.Meta title={u.name} description={LAYER_TYPES.find(l => l.key === u.type)?.label} />
                    </List.Item>
                  )}
                />
              ) : <Empty description="无上游节点" />
            },
            {
              key: 'downstream',
              label: '下游影响',
              children: impactData ? (
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
              )
            },
            {
              key: 'definition',
              label: '口径定义',
              children: selectedNode.description ? (
                <div className="fs12">{selectedNode.description}</div>
              ) : (
                <Empty description="暂无口径定义" />
              )
            }
          ]} />
        )}
      </Drawer>
    </div>
    </SkillPanel>
  );
};

export default LineagePage;
