/**
 * M3-05 前端对话面板
 * 气泡/输入中动画/推荐追问chips/历史弹窗/Token余量条
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Input, Button, Badge, List, Typography, Space, Spin,
  Popover, Progress, Tag, Tooltip, Empty, Upload, message as antMessage,
  Alert
} from 'antd';
import {
  SendOutlined, HistoryOutlined, LoadingOutlined,
  BulbOutlined, BarChartOutlined, PieChartOutlined,
  RiseOutlined, FallOutlined, WarningOutlined,
  PictureOutlined, ThunderboltFilled, CloseOutlined
} from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import './ChatPanel.css';

const { Text, Title } = Typography;
const { TextArea } = Input;

// AI 调用失败时的报错与用户选择信息
interface AiError {
  stage: string;
  error: string;
  options: string[];  // ['retry', 'rule_fallback']
  message: string;
}

// 消息类型
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  intent_type?: string;
  action?: any;
  suggested_followups?: string[];
  images?: string[];  // 图片URL列表
  can_override?: boolean;  // 是否允许用户强制覆盖blocking约束
  original_message?: string;  // 原始用户消息（用于override重发）
  ai_error?: AiError | null;  // AI 调用失败时携带，前端渲染报错卡+选择
}

// Token状态
interface TokenStatus {
  daily_limit: number;
  used_today: number;
  remaining: number;
  usage_percent: number;
  is_exhausted: boolean;
  is_warning: boolean;
}

// 对话面板属性
interface ChatPanelProps {
  sessionId?: string;
  dashboardId?: string;
  onAction?: (action: any) => void;
  onCollapse?: () => void; // 折叠对话面板（看板全屏）
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  sessionId: initialSessionId,
  dashboardId,
  onAction,
  onCollapse
}) => {
  // 状态
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(initialSessionId);
  const [tokenStatus, setTokenStatus] = useState<TokenStatus | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 获取Token状态
  const fetchTokenStatus = async () => {
    try {
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /tokens/status，按设计不带 token（过期 token 会打挂）
      const res = await fetch('/api/v1/tokens/status');
      const data = await res.json();
      if (data.quota) {
        setTokenStatus(data.quota);
      }
    } catch (e) {
      console.error('获取Token状态失败:', e);
    }
  };

  // 处理图片上传
  const handleImageUpload = (file: File) => {
    const isImage = file.type.startsWith('image/');
    if (!isImage) {
      antMessage.error('请上传图片文件');
      return false;
    }
    const isLt10M = file.size / 1024 / 1024 < 10;
    if (!isLt10M) {
      antMessage.error('图片不能超过10MB');
      return false;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const url = e.target?.result as string;
      setUploadedImages(prev => [...prev, url]);
    };
    reader.readAsDataURL(file);
    return false;
  };

  const removeImage = (index: number) => {
    setUploadedImages(prev => prev.filter((_, i) => i !== index));
  };

  // 恢复历史会话：按看板找最近一次有消息的会话，回填消息列表
  const loadHistory = async () => {
    if (!dashboardId) return;
    try {
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /chat/*，按设计不带 token
      const res = await fetch(`/api/v1/chat/sessions/latest?dashboard_id=${encodeURIComponent(dashboardId)}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.success && data.session_id && data.messages?.length > 0) {
        setSessionId(data.session_id);
        setMessages(data.messages.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          timestamp: m.created_at,
          intent_type: m.intent_type || undefined
        })));
      }
    } catch (e) {
      console.error('恢复对话历史失败:', e);
    }
  };

  // 初始化
  useEffect(() => {
    fetchTokenStatus();
    loadHistory();
    // 每30秒刷新一次Token状态
    const interval = setInterval(fetchTokenStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 创建会话
  const createSession = async () => {
    try {
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /chat/*，按设计不带 token
      const res = await fetch('/api/v1/chat/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dashboard_id: dashboardId })
      });
      const data = await res.json();
      if (data.session_id) {
        setSessionId(data.session_id);
        return data.session_id;
      }
    } catch (e) {
      console.error('创建会话失败:', e);
    }
    return null;
  };

  // 发送消息
  const sendMessage = async (overrideMsg?: { text: string; override?: boolean; forceRuleFallback?: boolean }) => {
    const content = overrideMsg?.text || inputValue.trim();
    if (!content) return;

    // 检查Token是否耗尽
    if (tokenStatus?.is_exhausted) {
      antMessage.warning('Token已耗尽，请申请加量');
      return;
    }

    const images = overrideMsg ? [] : [...uploadedImages];
    if (!overrideMsg) {
      setInputValue('');
      setUploadedImages([]);
    }
    setIsLoading(true);

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: overrideMsg ? `[强制执行] ${content}` : content,
      timestamp: new Date().toISOString(),
      images: images.length > 0 ? images : undefined
    };
    setMessages(prev => [...prev, userMsg]);

    // 获取或创建会话
    let sid = sessionId;
    if (!sid) {
      sid = await createSession();
    }

    if (!sid) {
      antMessage.error('创建会话失败');
      setIsLoading(false);
      return;
    }

    // SSE流式请求
    try {
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /chat/*，按设计不带 token
      const res = await fetch('/api/v1/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sid,
          message: content,
          dashboard_id: dashboardId,
          override: overrideMsg?.override || false,
          force_rule_fallback: overrideMsg?.forceRuleFallback || false
        })
      });

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error('无法读取响应');
      }

      let assistantContent = '';
      let intentData: any = null;
      let suggestedFollowups: string[] = [];
      let canOverride = false;
      let aiError: AiError | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = new TextDecoder().decode(value);
        const lines = text.split('\n\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') continue;

            try {
              const event = JSON.parse(dataStr);

              if (event.event === 'intent_classified') {
                intentData = JSON.parse(event.data);
              } else if (event.event === 'feasibility_check_failed') {
                const data = JSON.parse(event.data);
                assistantContent = data.message;
                canOverride = data.can_override || false;
              } else if (event.event === 'complete') {
                const data = JSON.parse(event.data);
                assistantContent = data.message;
                suggestedFollowups = data.suggested_followups || [];
                aiError = data.ai_error || null;

                // 执行动作（包含render_updates）
                if (data.action && onAction) {
                  onAction({
                    ...data.action,
                    render_updates: data.render_updates || [],
                    new_config: data.new_config || {}
                  });
                }
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }

      // 添加助手消息
      const assistantMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: assistantContent,
        timestamp: new Date().toISOString(),
        intent_type: intentData?.intent_type,
        suggested_followups: suggestedFollowups,
        can_override: canOverride,
        original_message: canOverride ? content : (aiError ? content : undefined),
        ai_error: aiError
      };
      setMessages(prev => [...prev, assistantMsg]);

      // 刷新Token状态
      fetchTokenStatus();

    } catch (e) {
      console.error('发送消息失败:', e);
      antMessage.error('发送失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  // 点击推荐追问
  const handleFollowupClick = (text: string) => {
    setInputValue(text);
    // 自动发送
    setTimeout(() => sendMessage(), 100);
  };

  // 用户强制覆盖blocking约束，重新发送
  const handleOverride = (originalMessage: string) => {
    sendMessage({ text: originalMessage, override: true });
  };

  // 获取Token进度条颜色
  const getTokenProgressColor = () => {
    if (!tokenStatus) return '#1890ff';
    if (tokenStatus.is_exhausted) return '#ff4d4f';
    if (tokenStatus.is_warning) return '#faad14';
    return '#52c41a';
  };

  // 获取输入框状态
  const getInputStatus = () => {
    if (!tokenStatus) return { disabled: false, placeholder: '输入指令...' };
    if (tokenStatus.is_exhausted) {
      return {
        disabled: true,
        placeholder: 'Token已耗尽，请申请加量后继续'
      };
    }
    if (tokenStatus.is_warning) {
      return {
        disabled: false,
        placeholder: `Token即将耗尽(${tokenStatus.usage_percent.toFixed(0)}%)，建议申请加量`
      };
    }
    return { disabled: false, placeholder: '输入指令，如"把饼图改成柱图"' };
  };

  const inputStatus = getInputStatus();

  // 历史记录弹窗内容
  const historyContent = (
    <div className="chat-history-popup">
      {messages.length === 0 ? (
        <Empty description="暂无历史记录" />
      ) : (
        <List
          size="small"
          dataSource={messages}
          renderItem={item => (
            <List.Item className={`history-item ${item.role}`}>
              <div className="history-content">
                <Tag color={item.role === 'user' ? 'blue' : 'green'}>
                  {item.role === 'user' ? '我' : 'AI'}
                </Tag>
                <Text ellipsis style={{ maxWidth: 200 }}>
                  {item.content.slice(0, 50)}
                </Text>
              </div>
            </List.Item>
          )}
        />
      )}
    </div>
  );

  return (
    <div className="chat-panel">
      {/* 头部 */}
      <div className="chat-header">
        <div className="chat-header-left">
          <span className="chat-logo"><ThunderboltFilled /></span>
          <span className="chat-title">数据助手</span>
        </div>
        <div className="chat-header-actions">
          {/* Token余量条 */}
          {tokenStatus && (
            <Tooltip title={`已用: ${tokenStatus.used_today} / ${tokenStatus.daily_limit}`}>
              <div className="token-bar">
                <Progress
                  percent={tokenStatus.usage_percent}
                  size="small"
                  strokeColor={getTokenProgressColor()}
                  showInfo={false}
                  style={{ width: 60 }}
                />
                <Text type={tokenStatus.is_warning ? 'warning' : 'secondary'} style={{ fontSize: 11 }}>
                  {tokenStatus.is_exhausted ? '已耗尽' : `${tokenStatus.remaining}剩余`}
                </Text>
              </div>
            </Tooltip>
          )}
          {/* 历史记录 */}
          <Popover
            content={historyContent}
            title="对话历史"
            trigger="click"
            open={showHistory}
            onOpenChange={setShowHistory}
            placement="bottomRight"
          >
            <Tooltip title="对话历史"><button className="chip-btn"><HistoryOutlined /></button></Tooltip>
          </Popover>
          {/* 关闭对话面板 */}
          {onCollapse && (
            <Tooltip title="关闭对话面板">
              <button className="chip-btn chip-btn-collapse" onClick={onCollapse}>
                <CloseOutlined />
              </button>
            </Tooltip>
          )}
        </div>
      </div>

      {/* 消息列表 */}
      <div className="chat-messages">
        <div className="chat-messages-scroll">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <div className="chat-welcome-icon"><ThunderboltFilled /></div>
            <div className="chat-welcome-title">Hi，有什么可以帮你？</div>
            <div className="chat-welcome-sub">关于这个数据看板，你可以这样问我：</div>
            <div className="welcome-suggestions">
              {['把饼图改成柱图', '分析异常原因', '筛选华东地区'].map((text, i) => (
                <Tag
                  key={i}
                  className="suggestion-tag"
                  onClick={() => handleFollowupClick(text)}
                >
                  {text}
                </Tag>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, index) => (
          <div key={msg.id} className={`message-row ${msg.role}`}>
            <div className={`message-bubble ${msg.role}`}>
              {/* 角色标识 */}
              <div className="message-role">
                {msg.role === 'user' ? (
                  <Badge color="blue" text="我" />
                ) : (
                  <Badge color="green" text="AI" />
                )}
              </div>
              {/* 消息内容 */}
              <div className="message-content">{msg.content}</div>
              {/* AI 调用失败报错卡：清晰提示 + 把选择权交还用户 */}
              {msg.ai_error && (
                <Alert
                  type="error"
                  showIcon
                  style={{ marginTop: 8 }}
                  message="AI 调用失败"
                  description={
                    <div>
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginBottom: 8 }}>
                        {msg.ai_error.error}
                      </div>
                      <Space wrap>
                        <Button
                          size="small"
                          type="primary"
                          onClick={() => sendMessage({ text: msg.original_message || '', forceRuleFallback: false })}
                          disabled={isLoading}
                        >
                          重试 AI
                        </Button>
                        <Button
                          size="small"
                          onClick={() => sendMessage({ text: msg.original_message || '', forceRuleFallback: true })}
                          disabled={isLoading}
                        >
                          改用规则引导回复
                        </Button>
                      </Space>
                    </div>
                  }
                />
              )}
              {/* 强制执行按钮（blocking约束可被用户覆盖时） */}
              {msg.can_override && msg.original_message && (
                <div className="override-action">
                  <Button
                    type="primary"
                    danger
                    size="small"
                    icon={<WarningOutlined />}
                    onClick={() => handleOverride(msg.original_message!)}
                    disabled={isLoading}
                  >
                    仍然执行
                  </Button>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    强制覆盖约束，按您的要求执行
                  </Text>
                </div>
              )}
              {/* 图片展示 */}
              {msg.images && msg.images.length > 0 && (
                <div className="message-images">
                  {msg.images.map((img, i) => (
                    <div key={i} className="message-image-item">
                      <img src={img} alt={`msg-image-${i}`} />
                    </div>
                  ))}
                </div>
              )}
              {/* 时间 */}
              <div className="message-time">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
              {/* 推荐追问 */}
              {msg.suggested_followups && msg.suggested_followups.length > 0 && (
                <div className="followup-chips">
                  <Text type="secondary" style={{ fontSize: 12 }}>推荐追问：</Text>
                  <Space size={4} wrap>
                    {msg.suggested_followups.map((text, i) => (
                      <Tag
                        key={i}
                        className="followup-chip"
                        onClick={() => handleFollowupClick(text)}
                      >
                        {text}
                      </Tag>
                    ))}
                  </Space>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* 输入中动画 */}
        {isLoading && (
          <div className="message-row assistant">
            <div className="message-bubble assistant typing">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                思考中...
              </Text>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 输入区域 — 参考样式：大圆角容器 + 底部工具栏 + 快捷指令 chips */}
      <div className="chat-input-area">
        {/* 快捷指令 chips（参考样式：输入框上方快捷操作） */}
        <div className="chat-quick-actions">
          <button className="quick-action" onClick={() => handleFollowupClick('把饼图改成柱图')}>
            <BarChartOutlined /> 改图表
          </button>
          <button className="quick-action" onClick={() => handleFollowupClick('分析异常原因')}>
            <BulbOutlined /> 分析异常
          </button>
          <button className="quick-action" onClick={() => handleFollowupClick('筛选华东地区')}>
            <RiseOutlined /> 筛选地区
          </button>
        </div>

        {/* 已上传图片预览 */}
        {uploadedImages.length > 0 && (
          <div className="chat-image-preview">
            {uploadedImages.map((img, index) => (
              <div key={index} className="chat-image-item">
                <img src={img} alt={`upload-${index}`} />
                <button className="chat-image-remove" onClick={() => removeImage(index)}>×</button>
              </div>
            ))}
          </div>
        )}

        {/* 大圆角输入容器 + 底部工具栏 */}
        <div className="chat-composer-box">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: 'none' }}
            onChange={(e) => {
              const files = e.target.files;
              if (files) {
                Array.from(files).forEach(f => handleImageUpload(f));
              }
              e.target.value = '';
            }}
          />
          <TextArea
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onPressEnter={e => {
              if (!e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder={inputStatus.placeholder}
            disabled={inputStatus.disabled || isLoading}
            autoSize={{ minRows: 1, maxRows: 4 }}
            className="chat-input"
          />
          <div className="chat-composer-toolbar">
            <button
              type="button"
              className="composer-tool"
              title="上传图片"
              onClick={() => fileInputRef.current?.click()}
            >
              <PictureOutlined />
            </button>
            <div className="composer-toolbar-right">
              <span className="composer-hint-inline">Shift + Enter 换行</span>
              <button
                type="button"
                className="composer-send"
                onClick={() => sendMessage()}
                disabled={inputStatus.disabled || isLoading || !inputValue.trim()}
                title="发送"
              >
                {isLoading ? <LoadingOutlined /> : <SendOutlined />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Token耗尽提示 */}
      {tokenStatus?.is_exhausted && (
        <div className="token-exhausted-warning">
          <WarningOutlined /> Token已耗尽，
          <Button type="link" size="small">申请加量</Button>
        </div>
      )}
    </div>
  );
};

export default ChatPanel;