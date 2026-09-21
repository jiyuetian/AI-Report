"""3.6 深度补充：LLM 网关状态 —— 四态 + 可手动复检（一次性补丁，可重入）。

反例（上一版三态留下的三个缺口）：
① 初始态与失败态都是 null → 慢网络下用户看到"状态未知（健康检查未返回）"，
   实际请求还在飞。把"正在检测"谎报成"接口没返回"，违背 2.1/2.4 诚实原则。
② antd5 Tabs 默认 destroyInactiveTabPane=false，SettingsTab 保持挂载 →
   useEffect([]) 只跑一次。LLM 修好后回到设置页仍显示"不可达"，永不刷新。
③ res.llm_reachable 若为 0/1/"true"/"false"（不同后端序列化形态），
   typeof v === 'boolean' 会判为 null → 把"不可达"误报成"未知"。
"""
import io
import sys

P = 'frontend/src/views/admin/AdminPage.tsx'
s = io.open(P, encoding='utf-8').read()
orig = s


def sub(old, new, tag):
    global s
    if new in s:
        print('[skip] %s already applied' % tag)
        return
    if s.count(old) != 1:
        print('[fail] %s count=%d' % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new)
    print('[ok] %s applied' % tag)


# ---------- 1) 导入：useRef + ReloadOutlined ----------
sub(
    "import React, { useState, useEffect, useContext, useCallback } from 'react';",
    "import React, { useState, useEffect, useContext, useCallback, useRef } from 'react';",
    'step1a useRef',
)
sub(
    "  CheckCircleOutlined, ClockCircleOutlined, ThunderboltOutlined\n} from '@ant-design/icons';",
    "  CheckCircleOutlined, ClockCircleOutlined, ThunderboltOutlined,\n  ReloadOutlined, SyncOutlined\n} from '@ant-design/icons';",
    'step1b icons',
)

# ---------- 2) 状态机：三态 → 四态（loading / true / false / null）----------
OLD_2 = """  // 3.6：LLM 网关状态改为实时真取数（/health → llm_reachable）。
  // 此前写死"已启用"，在模型实际不可达时仍显示已启用——与 2.1/2.4 的诚实标注原则冲突。
  const [llmReachable, setLlmReachable] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    http.get<any>('/health')
      .then((res: any) => {
        if (!alive) return;
        const v = res?.llm_reachable ?? res?.data?.llm_reachable;
        setLlmReachable(typeof v === 'boolean' ? v : null);
      })
      .catch(() => { if (alive) setLlmReachable(null); });
    return () => { alive = false; };
  }, []);"""
NEW_2 = """  // 3.6：LLM 网关状态改为实时真取数（/health → llm_reachable）。
  // 此前写死"已启用"，在模型实际不可达时仍显示已启用——与 2.1/2.4 的诚实标注原则冲突。
  //
  // 深度补充（反例驱动）：
  //  ① 四态而非三态：loading（正在检测）与 null（检测完成但无结论）必须分开，
  //     否则慢网络下"正在检测"被显示成"健康检查未返回"，仍是失真表述。
  //  ② 可手动复检：antd5 Tabs 默认不销毁非激活面板，SettingsTab 保持挂载，
  //     useEffect([]) 只跑一次 → LLM 恢复可达后页面不会自愈，必须给复检入口。
  //  ③ 值形态兼容：后端可能返回 0/1/"true"/"false"，严格 typeof boolean 会把
  //     "不可达"误报为"未知"。
  const [llmLoading, setLlmLoading] = useState<boolean>(true);
  const [llmReachable, setLlmReachable] = useState<boolean | null>(null);
  const [llmCheckedAt, setLlmCheckedAt] = useState<string | null>(null);
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; };
  }, []);

  const checkLlm = useCallback(async () => {
    if (!aliveRef.current) return;
    setLlmLoading(true);
    try {
      const res: any = await http.get<any>('/health');
      if (!aliveRef.current) return;
      const raw = res?.llm_reachable ?? res?.data?.llm_reachable;
      const v =
        raw === true || raw === 1 || raw === 'true' || raw === '1' ? true
        : raw === false || raw === 0 || raw === 'false' || raw === '0' ? false
        : null;
      setLlmReachable(v);
      setLlmCheckedAt(
        new Date().toLocaleTimeString('zh-CN', { hour12: false })
      );
    } catch {
      if (!aliveRef.current) return;
      setLlmReachable(null);
      setLlmCheckedAt(null);
    } finally {
      if (aliveRef.current) setLlmLoading(false);
    }
  }, []);

  useEffect(() => { checkLlm(); }, [checkLlm]);"""
sub(OLD_2, NEW_2, 'step2 state machine')

# ---------- 3) 渲染：四态 + 检测时间 + 复检按钮 ----------
OLD_3 = """        {/* LLM 网关：实时真取数，三态（可达 / 不可达 / 未知），不谎报 */}
        <p>
          <strong>LLM网关:</strong>{' '}
          {llmReachable === true && <Tag color="green">已启用（实时检测可达）</Tag>}
          {llmReachable === false && <Tag color="red">当前不可达（将自动降级为规则生成）</Tag>}
          {llmReachable === null && <Tag color="default">状态未知（健康检查未返回）</Tag>}
        </p>"""
NEW_3 = """        {/* LLM 网关：实时真取数，四态（检测中 / 可达 / 不可达 / 未知），不谎报 */}
        <p>
          <strong>LLM网关:</strong>{' '}
          {llmLoading && (
            <Tag color="processing" icon={<SyncOutlined spin />}>
              正在检测…
            </Tag>
          )}
          {!llmLoading && llmReachable === true && (
            <Tag color="green">已启用（实时检测可达）</Tag>
          )}
          {!llmLoading && llmReachable === false && (
            <Tag color="red">当前不可达（将自动降级为规则生成）</Tag>
          )}
          {!llmLoading && llmReachable === null && (
            <Tag color="default">状态未知（健康检查未返回该字段）</Tag>
          )}
          {!llmLoading && llmCheckedAt && (
            <span style={{ marginLeft: 8, fontSize: 12, opacity: 0.65 }}>
              检测于 {llmCheckedAt}
            </span>
          )}
          <Button
            type="link"
            size="small"
            icon={<ReloadOutlined />}
            loading={llmLoading}
            onClick={checkLlm}
            style={{ marginLeft: 4 }}
          >
            重新检测
          </Button>
        </p>"""
sub(OLD_3, NEW_3, 'step3 render')

io.open(P, 'w', encoding='utf-8').write(s)
print('changed =', s != orig, 'len =', len(s))
