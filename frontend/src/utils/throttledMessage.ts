/**
 * throttledMessage —— 弹窗节流 / 合并展示（ISS-045 剩余 UX 项）
 *
 * 背景：对话中 LLM 限流/失败可能在极短时间内连续触发多条 antd message 弹窗，
 * 打断用户操作（ISS-045 现象「弹窗反复弹」）。后端根因已由 failover + JSON 防护消除，
 * 本工具从前端兜底：
 *   1) 去重：相同 key（默认 content+type）在 DEDUPE_MS 窗口内只弹一次；
 *   2) 合并：antd message 带稳定 key 时本身会原地更新而非堆叠；
 *   3) 节流：任意两条 toast 间隔不足 MIN_GAP_MS 时，仅保留最后一条稍后展示，
 *      避免 6 层 failover 告警在短时间内连发连弹。
 *
 * 用法：import { throttledMessage } from './throttledMessage';
 *      throttledMessage.error('发送失败，请重试', 'send-fail');
 */
import { message } from 'antd';

type MsgType = 'error' | 'warning' | 'info' | 'success' | 'loading';

const DEDUPE_MS = 4000; // 相同 key 去重窗口
const MIN_GAP_MS = 600; // 任意新 toast 最小间隔，防堆叠风暴

const lastByKey: Record<string, number> = {};
let lastAnyAt = 0;
let pendingTimer: ReturnType<typeof setTimeout> | null = null;
let pending: { type: MsgType; content: string; key?: string; duration?: number } | null = null;

function doShow(type: MsgType, content: string, key?: string, duration?: number) {
  lastAnyAt = Date.now();
  if (key) {
    message[type]({ content, key, duration });
  } else {
    message[type](content, duration);
  }
}

function emit(type: MsgType, content: string, key?: string, duration?: number) {
  const now = Date.now();
  const dk = key || `${type}:${content}`;
  // 1) 去重：窗口内相同 key 不再弹
  if (lastByKey[dk] && now - lastByKey[dk] < DEDUPE_MS) return;
  lastByKey[dk] = now;
  // 3) 节流：距上次任意 toast 不足间隔则排队（仅保留最后一条）
  const gap = now - lastAnyAt;
  if (gap < MIN_GAP_MS) {
    pending = { type, content, key, duration };
    if (!pendingTimer) {
      const wait = MIN_GAP_MS - gap;
      pendingTimer = setTimeout(() => {
        pendingTimer = null;
        const p = pending;
        pending = null;
        if (p) doShow(p.type, p.content, p.key, p.duration);
      }, wait);
    }
    return;
  }
  doShow(type, content, key, duration);
}

export const throttledMessage = {
  error: (content: string, key?: string, duration?: number) => emit('error', content, key, duration),
  warning: (content: string, key?: string, duration?: number) => emit('warning', content, key, duration),
  info: (content: string, key?: string, duration?: number) => emit('info', content, key, duration),
  success: (content: string, key?: string, duration?: number) => emit('success', content, key, duration),
  loading: (content: string, key?: string, duration?: number) => emit('loading', content, key, duration),
};
