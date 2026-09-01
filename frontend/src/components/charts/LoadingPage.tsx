/**
 * M2-12 Loading页 - 流式SSE接收五阶段进度(POST)
 * 5阶段进度切换 + 取消 + 进度详情
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Card, Progress, Button, Space, Typography, Steps, message } from 'antd';
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
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dashboardId, setDashboardId] = useState<string>('');
  const [timeoutHit, setTimeoutHit] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const lastProgressRef = useRef<number>(Date.now());

  // 30秒无进度超时检测
  useEffect(() => {
    if (isComplete || error) return;
    const timer = setInterval(() => {
      const elapsed = Date.now() - lastProgressRef.current;
      if (elapsed > 30000 && !timeoutHit) {
        setTimeoutHit(true);
        const errMsg = '生成看板超时（30秒无响应），请检查后端服务状态后重试';
        setError(errMsg);
        message.error(errMsg);
        abortRef.current?.abort();
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [isComplete, error, timeoutHit]);

  // 连接SSE（POST流式）
  useEffect(() => {
    if (!datasetId) return;

    const abortController = new AbortController();
    abortRef.current = abortController;

    const fetchSSE = async () => {
      try {
        const response = await fetch(`${API_BASE}/brain/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dataset_id: datasetId, user_id: 'current' }),
          signal: abortController.signal,
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          const errMsg = errData.detail?.message || errData.detail?.error || `请求失败 (${response.status})`;
          setError(errMsg);
          message.error(errMsg);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          setError('无法读取响应流');
          return;
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          
          // 解析SSE事件
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // 保留未完成行

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                handleEvent(data);
              } catch (e) {
                console.warn('[Loading] 解析SSE行失败:', line);
              }
            }
          }
        }

        // 处理剩余buffer
        if (buffer.startsWith('data: ')) {
          try {
            const data = JSON.parse(buffer.slice(6));
            handleEvent(data);
          } catch (e) {}
        }

      } catch (err: any) {
        if (err.name === 'AbortError') {
          console.log('[Loading] 请求已取消');
        } else {
          console.error('[Loading] SSE请求失败:', err);
          setError(err.message || '网络错误');
          message.error('生成看板请求失败');
        }
      }
    };

    fetchSSE();

    return () => {
      abortController.abort();
    };
  }, [datasetId, retryCount]);

  // 处理SSE事件
  const handleEvent = (data: any) => {
    console.log('[Loading] SSE事件:', data);
    
    // 收到任何进度事件都重置超时计时器
    lastProgressRef.current = Date.now();
    
    const stage = data.stage || '';
    const status = data.status || '';
    const msg = data.message || '';
    const pct = data.progress || 0;
    
    const stageIdx = STAGES.findIndex(s => s.key === stage);
    if (stageIdx >= 0) {
      setCurrentStageIdx(stageIdx);
    }
    
    setProgress(pct);

    // 更新详情
    if (stageIdx >= 0 && stageIdx < STAGES.length && msg) {
      setDetails(prev => {
        const next = [...prev];
        next[stageIdx] = msg;
        return next;
      });
    }

    // 完成
    if (stage === 'COMPLETE' && status === 'completed') {
      setIsComplete(true);
      setProgress(100);
      const did = data.detail?.dashboard_id;
      if (did) {
        setDashboardId(did);
        message.success('看板生成完成！');
        if (onComplete) {
          setTimeout(() => onComplete(did), 1000);
        }
      }
    }

    // 失败
    if (status === 'failed') {
      setError(msg);
      message.error(`生成失败: ${msg}`);
    }
  };

  const handleViewDashboard = () => {
    if (dashboardId) {
      window.location.href = `/dashboard?id=${dashboardId}`;
    } else if (onComplete) {
      onComplete('');
    }
  };

  const handleRetry = () => {
    setError(null);
    setTimeoutHit(false);
    setProgress(0);
    setCurrentStageIdx(0);
    setDetails(STAGES.map(() => '等待中...'));
    setIsComplete(false);
    setRetryCount(c => c + 1);
  };

  return (
    <div className="loading-page">
      <Card className="loading-card" bordered={false}>
        {/* 头部 */}
        <div className="loading-header">
          <Title level={4}>
            {isComplete ? (
              <><CheckCircleOutlined style={{ color: '#52c41a' }} /> 看板生成完成</>
            ) : error ? (
              <><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> 看板生成失败</>
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
            status={error ? 'exception' : (isComplete ? 'success' : 'active')}
            strokeColor="#1677ff"
            trailColor="#e8e8e8"
            strokeWidth={12}
          />
          <div className="progress-label">
            <Text strong style={{ fontSize: 18 }}>{progress}%</Text>
            <Text type="secondary" style={{ marginLeft: 8 }}>
              {error ? error : (isComplete ? '看板生成完成！' : `${STAGES[currentStageIdx]?.name}中...`)}
            </Text>
          </div>
        </div>

        {/* 步骤条 */}
        <div className="steps-container">
          <Steps
            current={currentStageIdx}
            status={error ? 'error' : (isComplete ? 'finish' : 'process')}
            direction="vertical"
            size="small"
            items={STAGES.map((stage, i) => ({
              title: (
                <span>
                  {stage.name}
                  {i === currentStageIdx && !isComplete && !error && (
                    <LoadingOutlined style={{ marginLeft: 8, color: '#1677ff' }} />
                  )}
                  {(i < currentStageIdx || isComplete) && (
                    <CheckCircleOutlined style={{ marginLeft: 8, color: '#52c41a' }} />
                  )}
                </span>
              ),
              description: (
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {error && i >= currentStageIdx
                    ? (i === currentStageIdx ? error : '处理中断')
                    : details[i]}
                </Text>
              ),
            }))}
          />
        </div>

        {/* 操作按钮 */}
        <div className="loading-actions">
          <Space>
            {!isComplete && !error && onCancel && (
              <Button onClick={() => { abortRef.current?.abort(); onCancel(); }} danger>
                取消生成
              </Button>
            )}
            {!isComplete && error && (
              <>
                <Button onClick={() => { if (abortRef.current) abortRef.current.abort(); onCancel?.(); }} danger>
                  取消生成
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

        <div className="cancel-hint">
          <Text type="secondary">
            取消后可在"生成历史"中查看进度
          </Text>
        </div>
      </Card>
    </div>
  );
};

export default LoadingPage;