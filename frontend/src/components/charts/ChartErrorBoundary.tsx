/**
 * 图表级错误边界（防白屏）
 * 2026-09-17 取长补短自 InsightDesk（web/src/components/ErrorBoundary.jsx）
 *
 * 单个图表渲染期 / effect 期抛出的异常会被这里兜住，用可读的占位替代「卡片白屏」，
 * 不影响看板内其他图表与整个页面。
 */
import React from 'react';

interface ChartErrorBoundaryProps {
  children: React.ReactNode;
  title?: string;
}

interface ChartErrorBoundaryState {
  error: Error | null;
}

export default class ChartErrorBoundary extends React.Component<
  ChartErrorBoundaryProps,
  ChartErrorBoundaryState
> {
  constructor(props: ChartErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ChartErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ChartErrorBoundary] 捕获图表渲染异常：', error, info);
  }

  handleReload = () => {
    this.setState({ error: null });
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      const msg = this.state.error?.message || String(this.state.error);
      return (
        <div
          style={{
            padding: 24,
            color: 'var(--app-text-2, #8c8c8c)',
            fontSize: 13,
            textAlign: 'center',
            minHeight: 120,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          <span>「{this.props.title || '图表'}」渲染失败</span>
          <span style={{ fontSize: 12, color: 'var(--app-text-3, #bfbfbf)', maxWidth: 320, wordBreak: 'break-word' }}>
            {msg}
          </span>
          <a onClick={this.handleReload} style={{ color: '#1890ff', cursor: 'pointer' }}>
            刷新重试
          </a>
        </div>
      );
    }
    return this.props.children;
  }
}
