/**
 * M2-12 Loading页 - 后台任务轮询(可离开页面恢复)
 * 任务在服务端后台执行，前端通过 run_id 轮询状态：
 * - 运行中：固定展示加载进度，离开再回来不变
 * - 已结束：展示最终结果（成功跳看板 / 失败引导重试）
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Card, Progress, Button, Space, Typography, message, Modal, Tag } from 'antd';
import {
  LoadingOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import './LoadingPage.css';
import { authHeaders } from '../../utils/request';

const { Title, Text } = Typography;

// 阶段定义（对齐PRD A03-01）
const STAGES = [
  { key: 'S1', name: '理解数据' },
  { key: 'S2', name: '生成目标' },
  { key: 'S3', name: '推荐图表' },
  { key: 'S4', name: '编排优化' },
  { key: 'S5', name: '评分验证' },
];

// 用datasetId隔离run_id，支持离开页面后重进恢复
const RUN_KEY = (datasetId: string) => `brain_run_${datasetId}`;

// 2026-09-18 修复"生成一次出现两个看板"：React.StrictMode 开发模式双挂载 effect，
// 会对同一数据集连发两次 POST /brain/run → 生成两个一模一样的看板。
// 模块级在途集合跨挂载实例共享（useRef 无法跨 StrictMode 的两次 mount）。
const inFlightRuns = new Set<string>();

interface LoadingPageProps {
  datasetId: string;
  datasetName?: string;
  onCancel?: () => void;
  onComplete?: (dashboardId: string) => void;
}

// 2026-09-18 修复：原写法有两个问题
// ① 变量名写成 VITE_API_BASE（其余文件均为 VITE_API_BASE_URL）→ 环境变量覆盖永远不生效
// ② 默认值是硬编码绝对地址 http://localhost:8000/api/v1 → 开发态绕过 vite 代理（/api 不生效）、
//    生产态会把请求打到访问者本机的 8000 端口。统一改为相对路径，与其他组件一致。
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const LoadingPage: React.FC<LoadingPageProps> = ({
  datasetId,
  datasetName = '数据集',
  onCancel,
  onComplete,
}) => {
  const [currentStageIdx, setCurrentStageIdx] = useState(0);
  const [progress, setProgress] = useState(0);
  const [details, setDetails] = useState<string[]>(STAGES.map(() => '等待中...'));
  const [phase, setPhase] = useState<'starting' | 'running' | 'completed' | 'failed' | 'cancelled'>('starting');
  const [dashboardId, setDashboardId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [aiAwaiting, setAiAwaiting] = useState<any>(null);
  // M2（拍板）：记录本次生成方式，用于完成态持久徽标（AI 生成 / 本次为规则生成）
  const [dashboardAiParticipated, setDashboardAiParticipated] = useState<boolean | null>(null);
  const runIdRef = useRef<string>('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const phaseRef = useRef<'starting' | 'running' | 'completed' | 'failed' | 'cancelled'>('starting');
  // 任务开始时间：用于按实测进度速率估算剩余时间（对齐原型"预计还需 N 秒"）
  const startRef = useRef<number>(Date.now());
  const [etaText, setEtaText] = useState('预计还需片刻');
  // 3.2a：ETA 平滑（EMA） + 进度卡住检测（长 AI 阶段进度长时间不推进时给诚实提示）
  const etaEmaRef = useRef<number | null>(null);
  const lastPctRef = useRef<number>(0);
  const lastPctTsRef = useRef<number>(Date.now());
  // 3.2c：加载中提前显示的生成方式（后端 S2 结束后即下发 generation_mode）
  const [genModeLive, setGenModeLive] = useState<string | null>(null);

  const clearPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  // 提交一次状态快照到界面（emitComplete: 完成时是否自动跳转）
  const applyStatus = useCallback((data: any, emitComplete: boolean) => {
    const stage = data.stage || '';
    const status = data.status || '';
    const msg = data.message || '';
    const pct = Number(data.progress) || 0;
    // 3.2c：后端 S2 后下发 generation_mode（"ai" / "rule"），加载中即可知本次生成方式
    if (data.generation_mode) setGenModeLive(data.generation_mode);

    const stageIdx = STAGES.findIndex(s => s.key === stage);
    if (stageIdx >= 0) setCurrentStageIdx(stageIdx);
    setProgress(pct);
    // 3.2a：时间预估——用 EMA 平滑瞬时 rate（避免 2.5s 轮询间跳动），
    // 并检测"进度长时间未推进"（典型为 S3/S4b 等 AI 长阶段）：此时 rate 估算会失真，
    // 改为诚实提示"AI 阶段处理中，请稍候"，而不是给一个误导性的小数字。
    if (pct > 0 && pct < 100) {
      const now = Date.now();
      const elapsed = (now - startRef.current) / 1000;
      const inst = (elapsed * (100 - pct)) / pct; // 瞬时 eta（秒）
      const ema = etaEmaRef.current == null ? inst : etaEmaRef.current * 0.6 + inst * 0.4;
      etaEmaRef.current = ema;
      const prevTs = lastPctTsRef.current;
      const prevPct = lastPctRef.current;
      const stuck = pct === prevPct && (now - prevTs) > 10000;
      lastPctTsRef.current = now;
      lastPctRef.current = pct;
      if (stuck && elapsed > 15) {
        setEtaText('AI 阶段处理中，请稍候');
      } else {
        const v = Math.round(ema);
        setEtaText(v >= 1 ? `预计还需约 ${v} 秒` : '即将完成');
      }
    } else if (pct >= 100) {
      setEtaText('即将完成');
      etaEmaRef.current = null;
    }
    if (stageIdx >= 0 && msg) {
      setDetails(prev => {
        const next = [...prev];
        next[stageIdx] = msg;
        return next;
      });
    }

    if (status === 'completed') {
      clearPoll();
      setPhase('completed');
      phaseRef.current = 'completed';
      const did = data.detail?.dashboard_id || '';
      setDashboardId(did);
      if (!mountedRef.current) return;
      if (emitComplete) {
        const aiParticipated = data.detail?.generation_mode === "ai"
        setDashboardAiParticipated(!!aiParticipated)
        if (aiParticipated) {
          message.success('看板生成完成！');
        } else {
          message.warning('看板已用规则引擎生成（本次 AI 未参与，已自动兜底）');
        }
        if (onComplete) {
          setTimeout(() => onComplete(did), 800);
        }
      }
    } else if (status === 'failed') {
      clearPoll();
      setPhase('failed');
      phaseRef.current = 'failed';
      setError(msg || '生成失败，请重试');
    } else if (status === 'cancelled') {
      clearPoll();
      setPhase('cancelled');
      phaseRef.current = 'cancelled';
    } else if (status === 'unknown') {
      clearPoll();
      setPhase('failed');
      phaseRef.current = 'failed';
      // 后端已识别"中断/重启"语义，并按 dataset 自动反查了最近落库的看板
      // （若有命中，前端早已走 completed 分支；走到这里说明确实无看板可恢复）
      const interrupted = data?.detail?.interrupted;
      setError(
        interrupted
          ? '任务已被服务端清理（可能因后端重启或进程中断），请重新生成'
          : '未找到该后台任务（可能已被清除），请重新生成'
      );
    } else {
      setPhase('running');
      phaseRef.current = 'running';
    }

    // AI 失败暂停：后端在 S3 等阶段检测到 AI 不可用并等待用户抉择时，
    // /status 会带 ai_awaiting；在此弹出选择框，把决策权交还用户。
    if (data.ai_awaiting && status !== 'completed' && status !== 'failed' && status !== 'cancelled' && status !== 'unknown') {
      setAiAwaiting(data.ai_awaiting);
    } else {
      setAiAwaiting(null);
    }
  }, [onComplete]);

  // 查询单次状态
  const fetchStatus = useCallback(async (runId: string, emitComplete: boolean = true) => {
    try {
      // 带 dataset_id 让后端在 run_id 找不到（后端重启/中断）时，能按 dataset 自动反查最近看板
      const url = datasetId
        ? `${API_BASE}/brain/run/${runId}/status?dataset_id=${encodeURIComponent(datasetId)}`
        : `${API_BASE}/brain/run/${runId}/status`;
      // 后端该端点强制鉴权，裸 fetch 必须带 Authorization，否则登录态下必 401
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 GET /brain/run/{id}/status，已带 authHeaders()
      const res = await fetch(url, { headers: authHeaders() });
      const data = await res.json();
      if (mountedRef.current) applyStatus(data, emitComplete);
    } catch (e) {
      // 瞬态错误忽略，轮询继续
    }
  }, [applyStatus, datasetId]);

  // 启动轮询
  const startPoll = useCallback((runId: string) => {
    clearPoll();
    pollRef.current = setInterval(() => fetchStatus(runId, true), 2500);
  }, [fetchStatus]);

  // 启动一个新任务
  const startRun = useCallback(async () => {
    if (!datasetId) return;
    // 2026-09-18 修复"生成一次出现两个看板"：React.StrictMode 开发模式会双挂载 effect，
    // 对同一数据集连发两次 POST /brain/run → 生成两个一模一样的看板。
    // 模块级在途集合 + 同步占位 localStorage，保证同一数据集同一时刻只启动一次。
    if (inFlightRuns.has(datasetId)) return;
    inFlightRuns.add(datasetId);
    phaseRef.current = 'starting';
    setPhase('starting');
    setProgress(0);
    setCurrentStageIdx(0);
    setDetails(STAGES.map(() => '等待中...'));
    // 3.2a / 3.2c：新任务重置 ETA 平滑状态与加载中生成方式徽标
    setGenModeLive(null);
    etaEmaRef.current = null;
    lastPctRef.current = 0;
    lastPctTsRef.current = Date.now();
    try {
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 POST /brain/run，已带 authHeaders()
      const res = await fetch(`${API_BASE}/brain/run`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ dataset_id: datasetId, user_id: 'current' }),
      });
      const data = await res.json();
      if (!res.ok) {
        setPhase('failed');
        phaseRef.current = 'failed';
        setError(data.detail?.message || `开始失败 (${res.status})`);
        return;
      }
      runIdRef.current = data.run_id;
      localStorage.setItem(RUN_KEY(datasetId), data.run_id);
      setPhase('running');
      phaseRef.current = 'running';
      // 立即查询一次；仅当仍为运行中才轮询
      await fetchStatus(data.run_id, true);
      if (mountedRef.current && phaseRef.current === 'running') {
        startPoll(data.run_id);
      }
    } catch (e) {
      setPhase('failed');
      phaseRef.current = 'failed';
      setError('无法连接后台任务（网络异常）');
    } finally {
      inFlightRuns.delete(datasetId);
    }
  }, [datasetId, fetchStatus, startPoll]);

  // 挂载逻辑：有run_id则恢复（已完成不自动跳转），否则新起
  useEffect(() => {
    mountedRef.current = true;
    if (!datasetId) return;

    const storedRunId = localStorage.getItem(RUN_KEY(datasetId));
    if (storedRunId) {
      // 恢复模式：先查一次状态；已完成则展示结果不自动跳转，运行中才轮询
      runIdRef.current = storedRunId;
      fetchStatus(storedRunId, false).then(() => {
        if (mountedRef.current && phaseRef.current === 'running') {
          startPoll(storedRunId);
        }
      });
    } else {
      startRun();
    }

    return () => {
      mountedRef.current = false;
      clearPoll();
    };
  }, [datasetId, retryCount, fetchStatus, startPoll, startRun]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleViewDashboard = () => {
    localStorage.removeItem(RUN_KEY(datasetId));
    if (dashboardId) {
      window.location.href = `/dashboard?id=${dashboardId}`;
    } else if (onComplete) {
      onComplete('');
    }
  };

  const handleRetry = () => {
    localStorage.removeItem(RUN_KEY(datasetId));
    setError(null);
    setDashboardId('');
    setRetryCount(c => c + 1);
  };

  const handleCancel = async () => {
    const runId = runIdRef.current;
    if (runId) {
      try {
        // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 cancel，已带 authHeaders()
        await fetch(`${API_BASE}/brain/run/${runId}/cancel`, { method: 'POST', headers: authHeaders() });
      } catch (e) { /* 忽略 */ }
      localStorage.removeItem(RUN_KEY(datasetId));
    }
    clearPoll();
    setPhase('cancelled');
    setAiAwaiting(null);
    onCancel?.();
  };

  // AI 失败暂停时，用户回传选择（规则兜底生成 / 等 AI 恢复重试）
  const handleAiResume = async (choice: string) => {
    const runId = runIdRef.current;
    if (!runId) return;
    setAiAwaiting(null); // 先关弹窗，等待流水线继续（轮询会刷新进度）
    try {
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 resume，已带 authHeaders()
      await fetch(`${API_BASE}/brain/run/${runId}/resume`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ choice }),
      });
    } catch (e) {
      /* 忽略瞬态错误，流水线侧有超时兜底 */
    }
  };

  const isComplete = phase === 'completed';
  const isError = phase === 'failed' || phase === 'cancelled';

  // 各阶段默认文案（对齐原型；后端 detail 就绪后覆盖）
  const DEFAULT_DESC = [
    '识别字段的业务含义 · 判定数据主题',
    '产出候选分析目标：逾期监控 / 渠道对比 / 抵押风险…',
    '规则矩阵 + LLM 双驱动，逐张推荐图表',
    '选 KPI → 去冗余 → 分层 → 结论→佐证→明细',
    '看板评分卡校验（冗余/覆盖/叙事，≥70 分通过）',
  ];

  // 步骤状态：done / active / pending
  const stepStatusOf = (i: number): 'done' | 'active' | 'pending' => {
    if (isComplete) return 'done';
    if (isError) return i < currentStageIdx ? 'done' : i === currentStageIdx ? 'active' : 'pending';
    return i < currentStageIdx ? 'done' : i === currentStageIdx ? 'active' : 'pending';
  };

  const heroIcon = isComplete ? '✅' : isError ? (phase === 'cancelled' ? '⏹' : '⚠️') : '✨';
  const heroTitle = isComplete
    ? '看板生成完成'
    : isError
      ? (phase === 'cancelled' ? '任务已取消' : '看板生成失败')
      : '正在为你生成看板…';
  const heroSub = isComplete
    ? '正在为你打开看板，也可点击下方按钮直接查看'
    : isError
      ? (error || '生成失败，请重试')
      : '正在以数据分析师视角，全程理解你的数据';

  return (
    <div className="loading-page">
      {/* 顶部：渐变星形图标 + 标题 + 副标题（对齐原型） */}
      <div className="lp-hero">
        <div className={`lp-hero-icon${isError ? ' error' : ''}`}>{heroIcon}</div>
        <Title level={3} style={{ marginBottom: 6 }}>{heroTitle}</Title>
        <Text type="secondary" style={{ fontSize: 14 }}>{heroSub}</Text>
      </div>

      {/* 白卡：五步加工链路 + 进度条 + 预计时间（对齐原型） */}
      <Card className="lp-card" bordered={false}>
        <div className="lp-steps">
          {STAGES.map((stage, i) => {
            const st = stepStatusOf(i);
            return (
              <div key={stage.key} className={`lp-step ${st}`}>
                <div className="lp-step-head">
                  <span className="lp-step-dot">
                    {st === 'done' ? (
                      <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
                    ) : st === 'active' ? (
                      <LoadingOutlined style={{ color: '#1677ff', fontSize: 16 }} />
                    ) : (
                      <span className="lp-dot-pending" />
                    )}
                  </span>
                  <span className="lp-step-name">{stage.name}</span>
                </div>
                <div className="lp-step-desc">
                  {isError && i >= currentStageIdx
                    ? (i === currentStageIdx ? (phase === 'cancelled' ? '任务已取消' : '处理失败') : '未执行')
                    : (details[i] && details[i] !== '等待中...' ? details[i] : DEFAULT_DESC[i])}
                </div>
              </div>
            );
          })}
        </div>

        <Progress
          percent={progress}
          status={isError ? 'exception' : (isComplete ? 'success' : 'active')}
          strokeColor="#1677ff"
          trailColor="#e8e8e8"
          strokeWidth={8}
          showInfo={false}
        />
        <div className="lp-progress-meta">
          <Text type="secondary" style={{ fontSize: 13 }}>
            {isError
              ? (phase === 'cancelled' ? '任务已取消' : '看板生成失败')
              : (isComplete ? '看板生成完成！' : (
                <span>
                  {`正在：${STAGES[currentStageIdx]?.name}（第 ${currentStageIdx + 1}/5 步） · ${etaText}${retryCount > 0 ? ` · 已自动重试 ${retryCount} 次` : ''}`}
                  {genModeLive && (
                    <Tag
                      color={genModeLive === 'ai' ? 'green' : 'default'}
                      style={{ marginLeft: 8 }}
                    >
                      {genModeLive === 'ai' ? '智能增强生成中' : '规则引擎生成中'}
                    </Tag>
                  )}
                </span>
              ))}
          </Text>
          <Text strong style={{ fontSize: 15, color: '#1677ff' }}>{progress}%</Text>
          {/* M2（拍板）：完成态持久徽标 —— 一眼区分 AI 生成 / 规则兜底生成 */}
          {isComplete && (
            dashboardAiParticipated ? (
              <Tag color="green" style={{ marginLeft: 8 }}>已生成</Tag>
            ) : (
              <Tag color="default" style={{ marginLeft: 8 }}>本次为规则生成</Tag>
            )
          )}
        </div>
      </Card>

      {/* 操作按钮（对齐原型：取消生成 + 跳过等待） */}
      <div className="lp-actions">
        {isComplete ? (
          <Button type="primary" size="large" onClick={handleViewDashboard}>
            查看看板 →
          </Button>
        ) : isError ? (
          <>
            <Button size="large" onClick={handleCancel}>取消</Button>
            <Button type="primary" size="large" onClick={handleRetry}>重新尝试</Button>
          </>
        ) : (
          <>
            <Button size="large" onClick={handleCancel}>取消生成</Button>
            <Button
              type="primary"
              size="large"
              onClick={() => { window.location.href = '/dashboards'; }}
            >
              跳过等待，直接查看看板 →
            </Button>
          </>
        )}
      </div>

      {/* 异常兜底说明（对齐原型底部文案） */}
      <div className="lp-foot-hint">
        异常兜底：AI 超时自动重试 ≤3 次 → 仍失败提示「AI 服务暂停」；图表生成失败 ≤2 次重试 → 降级为简单图
      </div>

      {/* AI 失败暂停：用户选择弹窗（拍板1：允许关闭，关闭=视为选择规则生成） */}
      <Modal
        title="AI 调用失败，请选择后续方式"
        open={!!aiAwaiting}
        closable={true}
        maskClosable={false}
        onCancel={() => handleAiResume('rule_fallback')}
        footer={null}
      >
        <p style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          {aiAwaiting?.message}
        </p>
        {aiAwaiting?.reason && (
          <p style={{ color: '#888', fontSize: 12, marginTop: 4 }}>
            失败原因：{aiAwaiting.reason}
          </p>
        )}
        <p style={{ color: '#999', fontSize: 12, marginTop: 8 }}>
          （关闭本窗口将视为选择「规则引擎生成」，看板会标注「本次为规则生成」）
        </p>
        <Space style={{ marginTop: 16 }}>
          <Button onClick={() => handleAiResume('rule_fallback')}>
            用规则引擎兜底生成基础看板
          </Button>
          <Button type="primary" onClick={() => handleAiResume('wait_retry')}>
            等待 AI 恢复后重试
          </Button>
          <Button danger onClick={handleCancel}>
            取消生成
          </Button>
        </Space>
      </Modal>
    </div>
  );
};

export default LoadingPage;