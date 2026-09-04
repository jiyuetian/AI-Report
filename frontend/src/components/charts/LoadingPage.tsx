/**
 * M2-12 Loading页 - 后台任务轮询(可离开页面恢复)
 * 任务在服务端后台执行，前端通过 run_id 轮询状态：
 * - 运行中：固定展示加载进度，离开再回来不变
 * - 已结束：展示最终结果（成功跳看板 / 失败引导重试）
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Alert, Card, Progress, Button, Space, Typography, Steps, message } from 'antd';
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import './LoadingPage.css';

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

interface LoadingPageProps {
  datasetId: string;
  datasetName?: string;
  onCancel?: () => void;
  onComplete?: (dashboardId: string) => void;
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1';

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
  const runIdRef = useRef<string>('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const phaseRef = useRef<'starting' | 'running' | 'completed' | 'failed' | 'cancelled'>('starting');

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

    const stageIdx = STAGES.findIndex(s => s.key === stage);
    if (stageIdx >= 0) setCurrentStageIdx(stageIdx);
    setProgress(pct);
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
        message.success('看板生成完成！');
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
      setError('未找到该后台任务（可能已被清除），请重新生成');
    } else {
      setPhase('running');
      phaseRef.current = 'running';
    }
  }, [onComplete]);

  // 查询单次状态
  const fetchStatus = useCallback(async (runId: string, emitComplete: boolean = true) => {
    try {
      const res = await fetch(`${API_BASE}/brain/run/${runId}/status`);
      const data = await res.json();
      if (mountedRef.current) applyStatus(data, emitComplete);
    } catch (e) {
      // 瞬态错误忽略，轮询继续
    }
  }, [applyStatus]);

  // 启动轮询
  const startPoll = useCallback((runId: string) => {
    clearPoll();
    pollRef.current = setInterval(() => fetchStatus(runId, true), 2500);
  }, [fetchStatus]);

  // 启动一个新任务
  const startRun = useCallback(async () => {
    if (!datasetId) return;
    phaseRef.current = 'starting';
    setPhase('starting');
    setProgress(0);
    setCurrentStageIdx(0);
    setDetails(STAGES.map(() => '等待中...'));
    try {
      const res = await fetch(`${API_BASE}/brain/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
        await fetch(`${API_BASE}/brain/run/${runId}/cancel`, { method: 'POST' });
      } catch (e) { /* 忽略 */ }
      localStorage.removeItem(RUN_KEY(datasetId));
    }
    clearPoll();
    setPhase('cancelled');
    onCancel?.();
  };

  const isComplete = phase === 'completed';
  const isError = phase === 'failed' || phase === 'cancelled';

  return (
    <div className="loading-page">
      <Card className="loading-card" bordered={false}>
        {/* 头部 */}
        <div className="loading-header">
          <Title level={4}>
            {isComplete ? (
              <><CheckCircleOutlined style={{ color: '#52c41a' }} /> 看板生成完成</>
            ) : isError ? (
              <><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> {phase === 'cancelled' ? '任务已取消' : '看板生成失败'}</>
            ) : (
              <><LoadingOutlined spin /> AI正在生成看板</>
            )}
          </Title>
          <Text type="secondary">
            数据集: {datasetName}
          </Text>
        </div>

        {/* 总进度条 */}
        <div className="overall-progress">
          <Progress
            percent={progress}
            status={isError ? 'exception' : (isComplete ? 'success' : 'active')}
            strokeColor="#1677ff"
            trailColor="#e8e8e8"
            strokeWidth={12}
          />
          <div className="progress-label">
            <Text strong style={{ fontSize: 18 }}>{progress}%</Text>
            <Text type="secondary" style={{ marginLeft: 8 }}>
              {isError ? (phase === 'cancelled' ? '任务已取消' : '看板生成失败') : (isComplete ? '看板生成完成！' : `${STAGES[currentStageIdx]?.name}中...`)}
            </Text>
          </div>
        </div>

        {/* 失败/取消时：独立错误横幅，仅展示一次，避免与进度和步骤重复拼接 */}
        {isError && (
          <Alert
            type={phase === 'cancelled' ? 'warning' : 'error'}
            showIcon
            style={{ marginBottom: 16 }}
            message={phase === 'cancelled' ? '任务已取消' : '看板生成失败'}
            description={
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {error || (phase === 'cancelled' ? '任务已取消' : '生成失败，请重试')}
              </div>
            }
          />
        )}

        {/* 步骤条 */}
        <div className="steps-container">
          <Steps
            current={currentStageIdx}
            status={isError ? 'error' : (isComplete ? 'finish' : 'process')}
            direction="vertical"
            size="small"
            items={STAGES.map((stage, i) => ({
              title: (
                <span>
                  {stage.name}
                  {i === currentStageIdx && !isComplete && !isError && (
                    <LoadingOutlined style={{ marginLeft: 8, color: '#1677ff' }} />
                  )}
                  {(i < currentStageIdx || isComplete) && (
                    <CheckCircleOutlined style={{ marginLeft: 8, color: '#52c41a' }} />
                  )}
                </span>
              ),
              description: (
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {isError && i >= currentStageIdx
                    ? (i === currentStageIdx ? (phase === 'cancelled' ? '任务已取消' : '处理失败') : '未执行')
                    : details[i]}
                </Text>
              ),
            }))}
          />
        </div>

        {/* 运行中常驻提示：可离开页面，任务后台继续 */}
        {!isComplete && !isError && (
          <div className="duration-hint">
            <LoadingOutlined spin style={{ color: '#1677ff', marginRight: 6 }} />
            <Text type="secondary" style={{ fontSize: 13 }}>
              任务在后台运行中，可离开本页；稍后回来即可查看进度与最终结果
            </Text>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="loading-actions">
          <Space>
            {!isComplete && !isError && (
              <Button onClick={handleCancel} danger>
                取消生成
              </Button>
            )}
            {!isComplete && isError && (
              <>
                <Button onClick={handleCancel} danger>
                  取消
                </Button>
                <Button type="primary" onClick={handleRetry}>
                  重新尝试
                </Button>
              </>
            )}
            {isComplete && (
              <Button type="primary" size="large" onClick={handleViewDashboard}>
                查看看板
              </Button>
            )}
          </Space>
        </div>

        {!isComplete && !isError && (
          <div className="cancel-hint">
            <Text type="secondary">
              关闭本页或离开，任务都不会中断；可在"重新生成看板"处随时回到该任务
            </Text>
          </div>
        )}
      </Card>
    </div>
  );
};

export default LoadingPage;