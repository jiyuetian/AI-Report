import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Card, Button, Tag, Table, Modal, Radio, Input, Space, Divider, Alert, message, Typography, Empty, Select, Tooltip, Progress, Spin } from 'antd'
import {
  CheckCircleOutlined, WarningOutlined, CloseCircleOutlined,
  ToolOutlined, ReloadOutlined, ThunderboltOutlined, LoadingOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'
// Phase 5：SkillPanel 薄壳收口（展示本面板由哪些后端 skill 驱动，暗色自动继承）
import SkillPanel from '../skills/SkillPanel'
import { API_BASE, authHeaders, authorizedFetch } from '../../utils/request'

// 后端返回的单个问题结构
export interface ApiQualityIssue {
  type: string
  severity: 'blocking' | 'warning'
  column: string
  row_count: number
  message: string
  detail?: string
  sample_values: string[]
  rule: string
  source?: 'rule' | 'ai'
  repair_options: RepairOption[]
  // 2026-09-18 产品化：每个问题附最多 5 条真实受影响样本，前端展开展示
  // 「原始数据第几行 + 清洗前的值 + 对应的问题 + 清洗后处理成的结果」
  samples?: QualitySample[]
  // Task #724：AI 补充检测证据链（后端 /check/ai 与 /issues 两条路径同构）
  ai_issue_id?: string
  plain_conclusion?: string
  basis?: string
  involved_columns?: string[]
  check_suggestion?: string
  evidence_filter?: { column: string; op: string; value: any }[]
  row_numbers?: number[]
  evidence_available?: boolean
  confirmation?: { decision?: string; note?: string; by?: string; at?: number }
  // #34：AI 签发的修复策略 + 已执行的修复记录
  repair_plan?: {
    strategy?: string; label?: string; description?: string
    reason?: string; risk?: string; target_value?: string; numeric_only?: boolean
  }
  repair?: { strategy?: string; label?: string; affected_rows?: number; at?: number }
  status?: string
}

// 单条受影响样本（产品化展示用）：原始行 + 清洗前/后
export interface QualitySample {
  row: number
  raw: string
  problem: string
  fixed: string | null
  action: 'modify' | 'delete' | 'keep' | 'mask'
}

// 单个修复方案
export interface RepairOption {
  strategy: string
  label: string
  description: string
  recommended?: boolean  // 后端标记的推荐方案（一键采纳批次用）
}

// 分组后的质检结果（按检测类型分组）
export interface GroupedCheckResult {
  key: string
  label: string
  source: 'rule' | 'ai'
  blocking: boolean  // 根据severity是否有blocking决定
  status: 'pass' | 'warn' | 'fail'
  issues: ApiQualityIssue[]
}

// 类型到显示标签映射
const TYPE_LABEL_MAP: Record<string, string> = {
  'null': '空值校验',
  'format': '格式校验',
  'unique': '唯一性校验',
  'range': '范围校验',
  'logic': '逻辑校验',
  'code': '码值校验',
  'timeliness': '及时性校验',
  'distribution': '分布校验',
  'ai': 'AI补充检测',
}

interface QualityCheckPanelProps {
  fileId: string
  fileName?: string
  datasetId?: string
  onProceed?: () => void
  onStatusChange?: (status: QualityCheckStatus) => void
  /**
   * 是否在 datasetId 就绪后自动跑一次质检（默认 true = 新上传的数据集）。
   * 传 false = 恢复的历史数据集：直接读取后端已存质检结果，不重跑、不弹 toast。
   */
  autoCheck?: boolean
}

// 质检状态摘要（供父组件读取，用于多报表状态标记）
export interface QualityCheckStatus {
  hasBlocking: boolean
  totalIssues: number
  passCount: number
  checkCount: number
  checked: boolean  // 是否已执行过质检
}

// API 基址统一由 utils/request.ts 提供（Task #713）

// 按 fileId 存储质检状态，不同文件独立
interface CheckState {
  checks: GroupedCheckResult[]
  fixedKeys: Set<string>
}
const checkStateMap = new Map<string, CheckState>()

function getStateForFile(fileId: string, defaultChecks: GroupedCheckResult[]): CheckState {
  if (!checkStateMap.has(fileId)) {
    checkStateMap.set(fileId, {
      checks: [...defaultChecks],
      fixedKeys: new Set(),
    })
  }
  return checkStateMap.get(fileId)!
}

function saveStateForFile(fileId: string, checks: GroupedCheckResult[], fixedKeys: Set<string>) {
  checkStateMap.set(fileId, { checks, fixedKeys })
}

// 后端返回的扁平化issues按type分组
function groupIssuesByType(apiIssues: ApiQualityIssue[]): GroupedCheckResult[] {
  const groups: Record<string, ApiQualityIssue[]> = {}
  
  for (const issue of apiIssues) {
    if (!groups[issue.type]) {
      groups[issue.type] = []
    }
    groups[issue.type].push(issue)
  }
  
  const result: GroupedCheckResult[] = []
  
  // 固定顺序：空值、格式、唯一性、范围、逻辑、码值、及时性、分布、AI检测
  // 2026-09-17 修复：此前 order 漏了 timeliness/distribution，后端检出的分布/及时性问题被静默丢弃不展示
  const order = ['null', 'format', 'unique', 'range', 'logic', 'code', 'timeliness', 'distribution', 'ai']
  
  for (const type of order) {
    const issues = groups[type] || []
    if (type === 'ai' && issues.length === 0) {
      continue  // AI检测无问题就不显示
    }
    
    // 判断是否为阻断项：只要有一个问题是blocking，则整个分组是blocking
    const hasBlocking = issues.some(i => i.severity === 'blocking')
    
    // 确定状态：有问题 → blocking → fail，否则 → warn；没问题 → pass
    let status: 'pass' | 'warn' | 'fail' = 'pass'
    if (issues.length > 0) {
      status = hasBlocking ? 'fail' : 'warn'
    }
    
    // 获取显示标签
    const label = TYPE_LABEL_MAP[type] || type
    
    result.push({
      key: type,
      label,
      source: issues[0]?.source || 'rule',
      blocking: hasBlocking,
      status,
      issues,
    })
  }
  
  return result
}

// 修复策略中文标签（B2 修改明细展示用）
const STRATEGY_LABEL_MAP: Record<string, string> = {
  keep_first: '保留首条(去重)', keep_last: '保留末条(去重)',
  fill_mean: '均值填充', fill_median: '中位数填充', fill_mode: '众数填充', fill_constant: '常量填充',
  fill_boundary: '边界截断', winsorize: '缩尾(Winsorize)', coerce_numeric: '数值化',
  convert_standard: '日期标准化', map_closest: '码值归一', set_today: '未来日期→今天',
  swap_values: '交换日期', drop: '删除空行',
  ai_repair_median: 'AI建议·中位数替换', ai_repair_mean: 'AI建议·均值替换',
  ai_repair_winsorize: 'AI建议·P1/P99缩尾', ai_repair_set_null: 'AI建议·置空',
  ai_repair_constant: 'AI建议·指定值替换',
}

// B2：把 before/after 统计快照渲染成可读摘要
function describeStats(b: any, a: any): string {
  if (!b || !a) return '-'
  const parts: string[] = []
  if (b.null_count !== undefined && b.null_count !== a.null_count)
    parts.push(`空值 ${b.null_count}→${a.null_count}`)
  if (b.distinct_count !== undefined && b.distinct_count !== a.distinct_count)
    parts.push(`去重 ${b.distinct_count}→${a.distinct_count}`)
  if (b.min !== undefined && (b.min !== a.min || b.max !== a.max))
    parts.push(`极值 ${b.min}~${b.max}→${a.min}~${a.max}`)
  return parts.length ? parts.join('，') : '无变化'
}

export default function QualityCheckPanel({
  fileId, fileName, datasetId, onProceed, onStatusChange, autoCheck = true,
}: QualityCheckPanelProps) {
  const [state, setState] = useState<CheckState>(() => getStateForFile(fileId, groupIssuesByType([])))
  const [checking, setChecking] = useState(false)
  const [checked, setChecked] = useState(false)
  const [aiStatus, setAiStatus] = useState<'idle' | 'running' | 'done' | 'failed'>('idle')
  // ISS-103：质检结果（规则+AI）未就绪前显示"等待提示页"，不直接把规则结果裸抛给用户——
  // 用户已离开本步后再补 AI 无意义。AI 失败/超时则明确标注"本次为规则兜底结果"。
  const [aiWaiting, setAiWaiting] = useState(false)
  // AI 参与状态可视化：done 后展示"AI 已参与，补充发现 N 个问题"，让用户感知 AI 是否参与
  const [aiIssueCount, setAiIssueCount] = useState<number | null>(null)
  // ISS-103：LLM 全链路失败时后端 status 仍为 done（summary.fallback_used=true），
  // 此时不能显示绿色"AI 已参与"，必须显示琥珀色兜底提示
  const [aiFallback, setAiFallback] = useState(false)
  // 等待页计时（给用户"通常 20–30 秒出结果"的确定感）
  const [aiElapsed, setAiElapsed] = useState(0)
  useEffect(() => {
    if (!aiWaiting) { setAiElapsed(0); return }
    const t = setInterval(() => setAiElapsed(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [aiWaiting])
  const [applyingPlan, setApplyingPlan] = useState(false)
  // 当前批量修复模式（用于分别控制两个按钮的 loading 态）：'blocking' | 'all'
  const [planMode, setPlanMode] = useState<'blocking' | 'all'>('all')
  // ISS-063：批量修复内联状态（超时/取消/重试/成功与部分失败均内联可见，不再只靠 message.loading）
  const [applyError, setApplyError] = useState<string | null>(null)
  const [applyResult, setApplyResult] = useState<{ success: number; failed: number; note?: string } | null>(null)
  const [applyElapsed, setApplyElapsed] = useState(0)
  // 问题3：修复完成后自动进入看板生成的过渡态（内联"正在生成看板…"反馈，避免只有 toast 无下文）
  const [generating, setGenerating] = useState(false)
  const planAbortRef = useRef<AbortController | null>(null)

  // 每条问题当前选中的处理方案：默认=后端标记的推荐方案，用户可在表格里下拉切换
  const [strategyMap, setStrategyMap] = useState<Record<string, string>>({})
  const issueKey = (checkKey: string, column: string) => `${checkKey}-${column}`
  const strategyOf = (checkKey: string, issue: ApiQualityIssue) => {
    const sel = strategyMap[issueKey(checkKey, issue.column)]
    if (sel) return sel
    const opts = issue.repair_options || []
    return (opts.find(o => o.recommended) || opts[0])?.strategy || ''
  }

  // 供轮询回调读取最新状态，避免闭包拿到过期值
  const stateRef = useRef(state)
  useEffect(() => { stateRef.current = state }, [state])
  const aiIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const runningRef = useRef(false)  // 防重入护栏：避免 StrictMode 双挂载 / 重复触发导致重复 toast

  // 同步状态（依赖fileId，确保状态落在正确文件下）
  const updateState = useCallback((newState: CheckState) => {
    setState(newState)
    saveStateForFile(fileId, newState.checks, newState.fixedKeys)
  }, [fileId])

  // 组件卸载时清理轮询
  useEffect(() => {
    return () => {
      if (aiIntervalRef.current) clearInterval(aiIntervalRef.current)
    }
  }, [])

  // 将AI补充检测结果合并进面板（规则结果已显示，无需重新请求）
  const mergeAiResult = useCallback((newAiIssues: ApiQualityIssue[]) => {
    const cur = stateRef.current
    const nonAi = cur.checks.flatMap(c => c.issues).filter(i => i.type !== 'ai')
    const grouped = groupIssuesByType([...nonAi, ...newAiIssues])
    const next = { checks: grouped, fixedKeys: cur.fixedKeys }
    updateState(next)
    stateRef.current = next
  }, [updateState])

  // 轮询AI补充检测结果（后台任务完成后自动合并）
  const pollAiResult = useCallback((dsId: string, silent = false) => {
    if (aiIntervalRef.current) clearInterval(aiIntervalRef.current)
    let attempts = 0
    // Task #728/#33：轮询上限由后端 ai_budget 单一真相源下发（chain_budget_s），
    // 前端不再写死 30s。默认 32 次（64s）兜底，拿到后端预算后按 (budget+8)/2 动态收敛。
    let maxAttempts = 32
    const timer = setInterval(async () => {
      attempts++
      try {
        const res = await authorizedFetch(`${API_BASE}/quality/check/ai/${dsId}`, { headers: authHeaders() })
        const data = await res.json()
        const backendBudget = Number(data.chain_budget_s)
        if (Number.isFinite(backendBudget) && backendBudget > 0) {
          maxAttempts = Math.ceil((backendBudget + 8) / 2)
        }
        if (data.status === 'done') {
          clearInterval(timer)
          aiIntervalRef.current = null
          setAiStatus('done')
          setAiWaiting(false)
          setAiIssueCount(Number(data.ai_issues_count) || 0)
          // Task #706：优先用后端统一契约 ai_badge_eligible（与看板/对话同源），
          // 老版本响应无该字段时再退回 llm_called。
          const _sum: any = data.summary || {}
          setAiFallback(_sum.ai_badge_eligible === true ? false
            : _sum.ai_badge_eligible === false ? true
            : !_sum.llm_called)
          const issues = (data.issues || []) as ApiQualityIssue[]
          mergeAiResult(issues)
          // #35：只对「尚未人工核对」的新问题提示；已确认/已忽略、以及生成看板前的
          // silent 重检都不再弹，且不重复提示同一批 issue_id。
          const signature = dsId + '|' + issues.map(x => x.ai_issue_id || '').sort().join(',')
          const unreviewed = Number(data.unreviewed_count)
          const pending = Number.isFinite(unreviewed) ? unreviewed : (data.ai_issues_count || 0)
          if (!silent && pending > 0 && aiToastSignatureRef.current !== signature) {
            aiToastSignatureRef.current = signature
            message.info({ content: `AI 补充发现 ${pending} 个待确认问题，请在下表中逐条核对`, key: 'qc' })
          }
        } else if (data.status === 'failed') {
          clearInterval(timer)
          aiIntervalRef.current = null
          setAiStatus('failed')
          setAiWaiting(false)
          if (!silent) message.warning('AI补充检测未完成（超时或服务暂不可用），本次展示规则兜底结果')
        }
        // running/pending：继续轮询
      } catch (e) {
        // 瞬态请求错误忽略，继续轮询
      }
      if (attempts >= maxAttempts) {
        clearInterval(timer)
        aiIntervalRef.current = null
        setAiStatus(s => (s === 'idle' || s === 'running') ? 'failed' : s)
        setAiWaiting(false)
      }
    }, 2000)
    aiIntervalRef.current = timer
  }, [mergeAiResult])
  // Task #724：AI 补充检测证据链 / 真实明细下钻弹窗
  // #35：同一批 AI 问题只提示一次，避免生成看板时重复弹 toast
  const aiToastSignatureRef = useRef<string>('')

  const [evidenceModal, setEvidenceModal] = useState<{
    open: boolean
    issue: ApiQualityIssue | null
  }>({ open: false, issue: null })
  const [evidenceData, setEvidenceData] = useState<any | null>(null)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  // #34：AI 修复策略执行态（策略可覆盖、常量值可手填）
  const [repairing, setRepairing] = useState(false)
  const [repairStrategy, setRepairStrategy] = useState('')
  const [repairTargetValue, setRepairTargetValue] = useState('')
  const [repairError, setRepairError] = useState<string | null>(null)

  const decisionTag = (d?: string) => {
    if (d === 'confirmed') return <Tag color="green">已确认属实</Tag>
    if (d === 'ignored') return <Tag>已标记无需处理</Tag>
    return <Tag color="blue">待人工核对</Tag>
  }

  // 打开明细下钻：向后端要「AI 当时看到的样本 + 从 DuckDB 真实查出的行」
  const openEvidence = async (issue: ApiQualityIssue) => {
    setEvidenceModal({ open: true, issue })
    setEvidenceData(null)
    setEvidenceError(null)
    if (!datasetId) { setEvidenceError('数据集未就绪，请稍后再试'); return }
    if (!issue.ai_issue_id) {
      setEvidenceError('这条 AI 问题没有证据编号，请重新执行一次质检后再查看')
      return
    }
    setEvidenceLoading(true)
    try {
      const res = await authorizedFetch(
        `${API_BASE}/quality/${datasetId}/ai-evidence/${encodeURIComponent(issue.ai_issue_id)}`,
        { headers: authHeaders() }
      )
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setEvidenceError(data?.detail?.message || '明细数据读取失败')
        return
      }
      setEvidenceData(data)
    } catch {
      setEvidenceError('明细数据读取失败（网络异常）')
    } finally {
      setEvidenceLoading(false)
    }
  }

  // 人工核对结论落库 + 同步本地面板状态，刷新后仍可读
  const confirmAiIssue = async (decision: 'confirmed' | 'ignored' | 'pending') => {
    const issue = evidenceModal.issue
    if (!datasetId || !issue?.ai_issue_id) return
    setConfirming(true)
    try {
      const res = await authorizedFetch(`${API_BASE}/quality/${datasetId}/ai-confirm`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_id: issue.ai_issue_id, decision }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        message.error(data?.detail?.message || '核对结果保存失败')
        return
      }
      const cur = stateRef.current
      const checks = cur.checks.map(c => ({
        ...c,
        issues: c.issues.map(i => i.ai_issue_id === issue.ai_issue_id
          ? { ...i, confirmation: data.confirmation } : i),
      }))
      const next = { checks, fixedKeys: cur.fixedKeys }
      updateState(next)
      stateRef.current = next
      setEvidenceData((prev: any) => prev ? { ...prev, confirmation: data.confirmation } : prev)
      message.success(
        decision === 'confirmed' ? '已确认问题属实'
          : decision === 'ignored' ? '已标记为无需处理' : '已撤销核对结论'
      )
    } catch {
      message.error('核对结果保存失败（网络异常）')
    } finally {
      setConfirming(false)
    }
  }


  // #34：确认属实后，按 AI 签发的策略由规则引擎定点修复命中行。
  // AI 不直接改数据；后端白名单校验 + 写清洗层（可回滚）+ 行级留痕。
  const applyAiRepair = async () => {
    const issue = evidenceModal.issue
    if (!datasetId || !issue?.ai_issue_id) return
    setRepairing(true)
    setRepairError(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/quality/${datasetId}/ai-repair`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          issue_id: issue.ai_issue_id,
          strategy: repairStrategy || undefined,
          target_value: repairTargetValue,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setRepairError(data?.detail?.message || '修复未执行，数据保持原样')
        return
      }
      const cur = stateRef.current
      const checks = cur.checks.map(c => ({
        ...c,
        issues: c.issues.map(i => i.ai_issue_id === issue.ai_issue_id
          ? { ...i, repair: data.repair, status: 'done' } as ApiQualityIssue : i),
      }))
      const next = { checks, fixedKeys: cur.fixedKeys }
      updateState(next)
      stateRef.current = next
      setEvidenceData((prev: any) => prev ? {
        ...prev, repair: data.repair, can_auto_repair: false,
      } : prev)
      loadChangeLog()
      message.success(`已按「${data.strategy_label}」修复 ${data.affected_rows} 行，原始层未动，可在清洗修改明细里查看前后对比`)
    } catch {
      setRepairError('修复请求失败（网络异常），数据保持原样')
    } finally {
      setRepairing(false)
    }
  }

  const [fixModal, setFixModal] = useState<{
    open: boolean
    checkKey: string
    issue: ApiQualityIssue | null
  }>({ open: false, checkKey: '', issue: null })
  const [selectedStrategy, setSelectedStrategy] = useState('')
  const [customValue, setCustomValue] = useState('')
  const [fixing, setFixing] = useState(false)
  // ISS-064：重置（撤销清洗）的二次确认弹窗与 loading 态
  const [resetModalOpen, setResetModalOpen] = useState(false)
  const [resetting, setResetting] = useState(false)

  // B2：清洗修复行级变更明细（ISS-051）——聚合/逐行切换
  const [changeLog, setChangeLog] = useState<any[]>([])
  const [changeLogOpen, setChangeLogOpen] = useState(false)
  const [changeView, setChangeView] = useState<'agg' | 'row'>('agg')
  const [changeLogLoading, setChangeLogLoading] = useState(false)
  const changeLogLoadedRef = useRef(false)
  
  // 切换文件时同步质检状态，并清理上一文件的AI轮询
  useEffect(() => {
    if (aiIntervalRef.current) {
      clearInterval(aiIntervalRef.current)
      aiIntervalRef.current = null
    }
    setAiStatus('idle')
    setAiWaiting(false)
    setAiFallback(false)
    const existing = getStateForFile(fileId, groupIssuesByType([]))
    setState(existing)
  }, [fileId])
  
  // 一次性守卫：同一 datasetId 只自动处理一次，避免切 tab / StrictMode 重复触发
  // 注意：守卫赋值必须发生在"实际执行"时（见自动质检 effect 内定时器回调），不能在 effect 顶部提前赋值，
  // 否则 cleanup 清掉定时器后重挂载会命中守卫直接 return，导致首次自动质检被永久跳过（ISS-062）
  const autoHandledRef = useRef<string>('')
  // 自动质检 404 后的 1.5s 重试定时器，随 effect cleanup 一起清理，避免组件卸载后悬空触发
  const autoRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 注：真正的自动质检 effect 定义在 runCheck / loadExisting 之后（声明顺序要求）
  
  // 统计阻断项
  const blockingChecks = state.checks.filter(c => c.blocking)
  const hasBlockingErrors = blockingChecks.some(c => c.status === 'fail')
  const totalIssues = state.checks.reduce((sum, c) => sum + c.issues.length, 0)
  const passCount = state.checks.filter(c => c.status === 'pass').length
  // 必拦项问题数（阻断类且未通过的检查里的全部问题）——底部"仅处理必拦项"按钮用
  const blockingIssueCount = state.checks
    .filter(c => c.blocking && c.status === 'fail')
    .reduce((sum, c) => sum + c.issues.length, 0)
  
  // 向父组件报告质检状态（用于多报表Tab标记）
  useEffect(() => {
    if (onStatusChange) {
      onStatusChange({
        hasBlocking: hasBlockingErrors,
        totalIssues,
        passCount,
        checkCount: state.checks.length,
        checked,
      })
    }
  }, [hasBlockingErrors, totalIssues, passCount, state.checks.length, checked])
  
  // 重新质检 — 规则检测秒回，AI补充检测后台异步合并
  // 返回本次检测分组后的结果（供批量修复后判断是否可继续流转），失败返回 null
  const runCheck = useCallback(async (opts?: { silent?: boolean }): Promise<GroupedCheckResult[] | null> => {
    // silent=true：自动/恢复场景，不弹任何 toast，只更新面板状态
    const silent = opts?.silent === true
    if (!datasetId) {
      message.warning('数据集未创建，请等待预览完成')
      return null
    }
    if (runningRef.current) return null
    runningRef.current = true
    setChecking(true)
    setAiStatus('running')
    setAiWaiting(true)
    setAiFallback(false)
    // 静默模式不弹 toast；非静默也只给 8 秒兜底时长，避免异常路径下永久卡住
    if (!silent) {
      message.loading({ content: '正在进行质检（规则 + AI 合并反馈，通常 10–25 秒）...', key: 'qc', duration: 8 })
    }
    // 规则检测很快，仅保留45秒兜底超时，避免按钮卡在loading
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 45000)
    try {
      const response = await authorizedFetch(`${API_BASE}/quality/check`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: datasetId }),
        signal: ctrl.signal,
      })
      const data = await response.json()

      if (!response.ok) {
        if (!silent) {
          message.destroy('qc')
          message.error(data.detail?.message || '质检失败')
        }
        setAiStatus('failed')
        return null
      }

      // 后端秒回规则检测结果，分组处理
      const apiIssues: ApiQualityIssue[] = data.issues || []
      const grouped = groupIssuesByType(apiIssues)

      const newState: CheckState = {
        checks: grouped,
        fixedKeys: new Set(),
      }

      updateState(newState)
      stateRef.current = newState
      setChecked(true)

      // ISS-103：规则结果先落地，等待页继续展示直至 AI 就绪（不弹"规则完成"打断等待页体验）
      if (!silent) {
        message.destroy('qc')
      }
      // 启动后台轮询，AI结果就绪后结束等待页并展示完整结果
      pollAiResult(datasetId, silent)
      return grouped
    } catch (error: any) {
      if (!silent) {
        message.destroy('qc')
        if (error?.name === 'AbortError') {
          message.error('质检超时，请重试')
        } else {
          message.error('质检请求失败')
        }
      }
      setAiStatus('failed')
      setAiWaiting(false)
      return null
    } finally {
      clearTimeout(timer)
      setChecking(false)
      runningRef.current = false
    }
  }, [fileId, fileName, datasetId, pollAiResult])

  // 读取后端已存储的质检结果（恢复历史数据集时用：不重跑规则检测、不弹 toast）
  // 返回问题条数；无已存结果 / 请求失败返回 null，由调用方决定是否兜底跑一次
  const loadExisting = useCallback(async (): Promise<number | null> => {
    if (!datasetId) return null
    try {
      const res = await authorizedFetch(`${API_BASE}/quality/${datasetId}/issues`, { headers: authHeaders() })
      if (!res.ok) return null
      const data = await res.json()
      const raw = (data?.issues || []) as any[]
      if (!Array.isArray(raw)) return null
      const apiIssues: ApiQualityIssue[] = raw.map((i: any) => ({
        type: i.type || 'unknown',
        severity: (i.severity === 'blocking' ? 'blocking' : 'warning') as 'blocking' | 'warning',
        column: i.field_name || i.column || '',
        row_count: Number(i.affect_rows ?? i.row_count ?? 0),
        message: i.message || '',
        detail: i.detail || '',
        sample_values: i.sample_values || [],
        rule: i.rule || '',
        source: (i.source === 'ai' ? 'ai' : 'rule') as 'rule' | 'ai',
        repair_options: i.repair_options || [],
        ai_issue_id: i.ai_issue_id || '',
        plain_conclusion: i.plain_conclusion || '',
        basis: i.basis || '',
        involved_columns: i.involved_columns || [],
        check_suggestion: i.check_suggestion || '',
        evidence_available: !!i.evidence_available,
        confirmation: i.confirmation || { decision: 'pending' },
        evidence_filter: i.evidence_filter || [],
        row_numbers: i.row_numbers || [],
        repair_plan: i.repair_plan || {},
        repair: i.repair || {},
        status: i.status || 'todo',
      }))
      const newState: CheckState = { checks: groupIssuesByType(apiIssues), fixedKeys: new Set() }
      updateState(newState)
      stateRef.current = newState
      setChecked(true)
      return apiIssues.length
    } catch {
      return null
    }
  }, [datasetId, updateState])

  // B2：拉取清洗修复的行级变更明细（before/after 快照）
  const loadChangeLog = useCallback(async () => {
    if (!datasetId) return
    setChangeLogLoading(true)
    try {
      const res = await authorizedFetch(`${API_BASE}/quality/${datasetId}/change-log?limit=200`, { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setChangeLog(data.change_logs || [])
      }
    } catch {
      // 忽略瞬时错误
    } finally {
      setChangeLogLoading(false)
    }
  }, [datasetId])

  // 自动质检：只对「新上传」的数据集跑一次；恢复的历史数据集直接读已存结果（不重跑、不弹 toast）
  useEffect(() => {
    if (!datasetId) return
    if (autoHandledRef.current === datasetId) return

    if (autoCheck === false) {
      // 历史数据集：先读已存结果（不重跑、不弹 toast）；无记录（如修复上线前的数据集）则静默兜底跑一次
      autoHandledRef.current = datasetId
      loadExisting().then(n => {
        if (n === null) runCheck({ silent: true })
      })
      return
    }

    // 新数据集：500ms 后自动跑一次；守卫在「实际执行」时才赋值，避免 cleanup 清定时器后重挂载
    // 命中守卫直接 return 而永久跳过（ISS-062）。若数据表尚未就绪（404/!ok），1.5s 后静默重试一次，
    // 仍失败则静默保留（不弹错误、不阻断），由用户手动点「重新质检」。
    const timer = setTimeout(() => {
      autoHandledRef.current = datasetId
      runCheck({ silent: true }).then(result => {
        if (result === null) {
          autoRetryRef.current = setTimeout(() => {
            runCheck({ silent: true })
          }, 1500)
        }
      })
    }, 500)
    return () => {
      clearTimeout(timer)
      if (autoRetryRef.current) {
        clearTimeout(autoRetryRef.current)
        autoRetryRef.current = null
      }
    }
  }, [datasetId, autoCheck, loadExisting, runCheck])
  
  const openFix = (checkKey: string, issue: ApiQualityIssue) => {
    setFixModal({ open: true, checkKey, issue })
    // 默认选推荐方案（无标记则选第一个）
    const rec = (issue.repair_options || []).find(o => o.recommended) || issue.repair_options[0]
    setSelectedStrategy(rec?.strategy || '')
    setCustomValue('')
  }
  
  // 修复 — 调用后端修复API；立即给出反馈，后端失败明确报错，不误报成功
  const applyFix = async () => {
    const { checkKey, issue } = fixModal
    if (!issue || !datasetId) {
      message.error('参数错误')
      return
    }

    // 立即反馈：按钮loading + 持续loading提示，避免"点了没反应"
    setFixing(true)
    message.loading({ content: '正在应用修复方案，请稍候...', key: 'fix', duration: 0 })
    try {
      const response = await authorizedFetch(`${API_BASE}/quality/fix`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset_id: datasetId,
          issue_type: checkKey,
          column: issue.column,
          fix_strategy: selectedStrategy,
        })
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        setFixing(false)
        message.destroy('fix')
        message.error(data.detail?.message || '修复失败，请重试')
        return  // 保留弹窗与问题，不误标成功
      }
    } catch (e) {
      setFixing(false)
      message.destroy('fix')
      message.error('修复请求失败（网络异常），请重试')
      return
    }

    // 后端修复成功 → 本地更新状态：移除该问题
    const newChecks = state.checks.map(check => {
      if (check.key === checkKey) {
        // 移除该问题
        const newIssues = check.issues.filter(i => i.column !== issue.column)
        // 重新判断状态
        const hasBlocking = newIssues.some(i => i.severity === 'blocking')
        let status: 'pass' | 'warn' | 'fail' = 'pass'
        if (newIssues.length > 0) {
          status = hasBlocking ? 'fail' : 'warn'
        }
        return { ...check, issues: newIssues, status, blocking: hasBlocking }
      }
      return check
    })

    const newFixedKeys = new Set(state.fixedKeys)
    newFixedKeys.add(`${checkKey}-${issue.column}`)

    updateState({
      checks: newChecks,
      fixedKeys: newFixedKeys,
    })

    message.destroy('fix')
    setFixModal({ open: false, checkKey: '', issue: null })
    setFixing(false)
    message.success(`已修复 ${issue.column}，问题移除`)
    loadChangeLog()
  }

  // 一键采纳推荐方案 — 对齐 B 的"推荐清洗计划"交互：后端已为每类问题标记 recommended 策略，
  // 这里汇总所有规则类问题生成推荐计划，批量调 /quality/fix-batch，完成后自动重跑质检刷新结果。
  // 2026-09-18：支持 onlyBlocking —— 对齐原型底部"仅处理必拦项，继续"，只批量修复阻断类问题。
  // 问题3：proceedAfter=true 时，修复成功后自动进入看板生成（一站式：修复+生成），并给出"正在生成"中间反馈
  const applyRecommendedPlan = useCallback(async (onlyBlocking: boolean = false, proceedAfter: boolean = false) => {
    if (!datasetId || checking) return
    const seen = new Set<string>()
    const plan: { issue_type: string; column: string; fix_strategy: string }[] = []
    for (const c of stateRef.current.checks) {
      if (c.source !== 'rule' || c.key === 'ai') continue  // AI补充问题置信度分层，不进自动批次
      if (onlyBlocking && !(c.blocking && c.status === 'fail')) continue  // 仅必拦项模式：跳过非阻断问题
      for (const i of c.issues) {
        // 已修复的跳过，避免重复处理
        if (stateRef.current.fixedKeys.has(`${c.key}-${i.column}`)) continue
        const opts = i.repair_options || []
        // 优先用用户在表格里下拉选中的方案，否则用后端推荐方案
        const manual = strategyMap[`${c.key}-${i.column}`]
        const rec = opts.find(o => o.recommended)
          || opts.find(o => o.strategy !== 'ignore' && o.strategy !== 'drop')
        const strategy = manual || rec?.strategy
        if (!strategy || strategy === 'ignore') continue  // "确认忽略"类问题不自动执行
        const key = `${c.key}-${i.column}-${strategy}`
        if (seen.has(key)) continue
        seen.add(key)
        plan.push({ issue_type: c.key, column: i.column, fix_strategy: strategy })
      }
    }
    if (!plan.length) {
      message.info('当前问题均无自动推荐方案，请逐条选择处理')
      return
    }
    // 重置上一次结果/错误，开始新的批量修复
    setApplyError(null)
    setApplyResult(null)
    setApplyElapsed(0)
    setApplyingPlan(true)
    // ISS-063：60s 超时 + 可取消；窗口内联状态条实时反馈进度
    const ctrl = new AbortController()
    planAbortRef.current = ctrl
    const stopwatch = setInterval(() => setApplyElapsed(e => e + 1), 1000)
    const timeout = setTimeout(() => ctrl.abort(), 60000)
    try {
      const resp = await authorizedFetch(`${API_BASE}/quality/fix-batch`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: datasetId, items: plan }),
        signal: ctrl.signal,
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setApplyError(data.detail?.message || '批量修复失败，请重试或逐条修复')
        return
      }
      // 内联展示成功 / 部分失败结果
      if (data.failed > 0) {
        setApplyResult({ success: data.success, failed: data.failed })
        // 问题3：部分失败时仍要给明确反馈，不再用"请点生成看板"误导（因为不会自动生成）
        message.warning(`已修复 ${data.success} 项，${data.failed} 项失败（可逐条处理）`)
      } else {
        setApplyResult({ success: data.success, failed: 0 })
        message.success(`已按推荐方案修复 ${data.success} 项`)
      }
      // C1：重新质检改为后台重检（不阻塞用户）。先立即展示成果，重检完成后由面板自动刷新状态。
      loadChangeLog()
      const newChecks = await runCheck({ silent: true })
      const remainBlocking = newChecks ? newChecks.some(c => c.blocking && c.status === 'fail') : false
      const remainWarn = newChecks ? newChecks.reduce((s, c) => s + c.issues.length, 0) : 0
      // 问题3：一键修复生成看板场景——修复成功后直接进看板生成，给出"正在生成"中间反馈；
      // 仅当无阻断项才自动进（有阻断残留时交给用户逐条处理，绝不静默跳过阻断）。
      if (proceedAfter) {
        if (!remainBlocking) {
          setGenerating(true)
          setApplyResult({ success: data.success, failed: 0 })
          // 移除冗余 toast：LoadingPage 会立即呈现"正在为你生成看板"，不再重复提示打断
          // 给一帧渲染时间，再打开 LoadingPage（真实生成进度由 LoadingPage 呈现）
          setTimeout(() => { onProceed?.(); setGenerating(false) }, 350)
        } else {
          message.warning('仍有阻断性问题未修复，已停止自动生成，请在下方表格逐条处理后继续')
        }
        return
      }
      if (!remainBlocking) {
        // 无阻断项 → 提示用户手动点「生成看板」（ISS-065：删除自动弹窗，避免打断用户操作流）
        message.success(
          remainWarn > 0
            ? `质检通过（无阻断项），剩余 ${remainWarn} 个非阻断提示已自动保留，请点「生成看板」继续`
            : '质检全部通过，请点「生成看板」继续'
        )
      } else {
        message.warning('仍有阻断性问题未修复，请在下方表格逐条处理后继续')
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        setApplyError('批量修复已取消（超时 60s 未响应或手动取消）')
      } else {
        setApplyError('批量修复请求失败（网络异常），请重试')
      }
    } finally {
      clearTimeout(timeout)
      clearInterval(stopwatch)
      planAbortRef.current = null
      setApplyingPlan(false)
    }
  }, [datasetId, checking, runCheck, strategyMap, onProceed, generating])

  // 重置 — 撤销清洗层，回滚到原始数据（ISS-064）
  // 仅清空前端状态不足以回滚，必须调用后端 /quality/{dataset_id}/reset 真正删除清洗层物理表 +
  // 将 QualityIssue.status 置 ignored，否则"修复写清洗层、重置未回滚"会留下脏数据。
  const resetAll = async () => {
    if (!datasetId) return
    setResetting(true)
    // 清理可能残留的 duration:0 提示（如批量修复的 'plan'），避免卡在界面
    message.destroy('plan')
    try {
      const resp = await authorizedFetch(`${API_BASE}/quality/${datasetId}/reset`, {
        method: 'POST',
        headers: authHeaders(),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        message.error(data.detail?.message || '重置失败，请重试')
        return
      }
      // 真实回滚成功后清空本地质检状态
      const newState: CheckState = { checks: groupIssuesByType([]), fixedKeys: new Set() }
      updateState(newState)
      setApplyError(null)
      setApplyResult(null)
      message.success('已重置：清洗层已撤销，数据回滚到原始状态，正在重新质检...')
      // 自动重跑质检，刷新面板（silent：不弹中间 loading，由面板状态反映）
      await runCheck({ silent: true })
    } catch (e) {
      message.error('重置请求失败（网络异常），请重试')
    } finally {
      setResetting(false)
      setResetModalOpen(false)
    }
  }
  
  const { Text } = Typography
  const fixCheck = state.checks.find(c => c.key === fixModal.checkKey)
  
  // B2：聚合视图（按 字段+策略 分组）
  const aggGroups = useMemo(() => {
    const m: Record<string, any> = {}
    for (const log of changeLog) {
      const key = `${log.field_name}__${log.strategy}`
      if (!m[key]) {
        m[key] = {
          field_name: log.field_name, strategy: log.strategy,
          issue_type: log.issue_type, count: 0, affected: 0,
          before: log.before_value, after: log.after_value,
        }
      }
      m[key].count += 1
      m[key].affected += (log.affected_rows || 0)
    }
    return Object.values(m)
  }, [changeLog])

  // 计算所有扁平化问题（用于表格展示）
  const allFlatIssues = state.checks.flatMap(check => 
    check.issues.map(issue => ({
      ...issue,
      checkLabel: check.label,
      checkKey: check.key,
      blocking: check.blocking,
      source: check.source,
    }))
  )
  
  // ISS-103：规则+AI 结果未就绪时显示等待提示页——用户在本步只看一次完整结果，不做"后补"；
  // AI 失败/超时由 pollAiResult 结束等待并转入兜底提示（见下方 failed banner）
  if (aiWaiting) {
    return (
      <SkillPanel panelKind="quality" title="数据质检">
        <Card
          title={
            <Space>
              <span>数据质检 {fileName && <Text type="secondary" style={{ fontWeight: 400 }}>— {fileName}</Text>}</span>
              <Tag icon={<LoadingOutlined spin />} color="processing">检测中</Tag>
            </Space>
          }
          style={{ marginTop: 0 }}
        >
          <div style={{ textAlign: 'center', padding: '56px 24px 64px' }}>
            <LoadingOutlined spin style={{ fontSize: 40, color: '#1677ff' }} />
            <div style={{ fontSize: 16, fontWeight: 600, marginTop: 16 }}>
              正在综合规则检测与 AI 补充检测…
            </div>
            <div style={{ fontSize: 13, color: '#8c8c8c', marginTop: 8 }}>
              规则检测已完成，AI 补充检测进行中，通常 10–25 秒返回；最长等待 30 秒，超时会明确提示并给出规则兜底结果
            </div>
            <div style={{ width: 320, margin: '24px auto 0' }}>
              <Progress
                percent={Math.min(95, Math.round((aiElapsed / 30) * 100))}
                status="active"
                format={() => `已等待 ${aiElapsed}s`}
              />
            </div>
          </div>
        </Card>
      </SkillPanel>
    )
  }

  return (
    <SkillPanel panelKind="quality" title="数据质检">
    <Card
      title={
        <Space>
          <span>数据质检 {fileName && <Text type="secondary" style={{ fontWeight: 400 }}>— {fileName}</Text>}</span>
          {totalIssues > 0 ? (
            <Tag icon={<WarningOutlined />} color="warning">{totalIssues} 个问题</Tag>
          ) : (
            <Tag icon={<CheckCircleOutlined />} color="success">全部通过</Tag>
          )}
        </Space>
      }
      extra={
        <Space>
          <Button size="small" onClick={() => setResetModalOpen(true)}>重置数据（撤销清洗）</Button>
          <Button icon={<ReloadOutlined />} loading={checking} onClick={() => runCheck()}>重新质检</Button>
        </Space>
      }
      style={{ marginTop: 0 }}
    >
      {/* ISS-103：让用户明确感知 AI 是否参与了本次质检 */}
      {aiStatus === 'done' && checked && aiIssueCount !== null && !aiFallback && (
        <Alert
          type="success"
          showIcon
          message={aiIssueCount > 0
            ? `AI 已参与质检：补充发现 ${aiIssueCount} 个规则外潜在问题（分布异常 / 语义异常 / 字段矛盾等）`
            : 'AI 已参与质检：未发现规则之外的补充问题'}
          style={{ marginBottom: 16 }}
        />
      )}
      {(aiStatus === 'failed' || (aiStatus === 'done' && aiFallback)) && checked && (
        <Alert
          type="warning"
          showIcon
          message="AI 补充检测未完成（超时或服务暂不可用），本次展示的是规则兜底检测结果"
          description="AI 可发现分布异常、语义异常、字段矛盾等规则覆盖不到的问题，本次未包含该部分；可点击右上角「重新质检」重试。"
          style={{ marginBottom: 16 }}
        />
      )}
      {hasBlockingErrors && (
        <Alert
          type="error"
          showIcon
          message="存在阻断性问题（主键重复/格式错误/AI严重问题），必须修复后才能继续生成看板"
          style={{ marginBottom: 16 }}
        />
      )}
      {!hasBlockingErrors && totalIssues > 0 && (
        <Alert
          type="warning"
          showIcon
          message="存在非阻断性提示，可选择修复或忽略后继续"
          style={{ marginBottom: 16 }}
        />
      )}

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: 16 }}>
        {state.checks.map(c => (
          <Card
            key={c.key}
            size="small"
            style={{
              borderColor: c.status === 'fail' ? '#ff4d4f' : c.status === 'warn' ? '#faad14' : '#d9d9d9',
              background: c.status === 'fail' ? '#fff2f0' : c.status === 'warn' ? '#fffbe6' : '#f6ffed',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 600 }}>
                {c.label}
                {c.source === 'ai' && <Tag color="blue" style={{ marginLeft: 4, fontSize: 10 }}>AI</Tag>}
              </span>
              {c.status === 'pass' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
               c.status === 'warn' ? <WarningOutlined style={{ color: '#faad14' }} /> :
               <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
            </div>
            <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
              {c.issues.length > 0 ? `${c.issues.length} 个问题` : '通过'}
              {c.blocking && <Tag color="red" style={{ marginLeft: 6, fontSize: 11 }}>阻断</Tag>}
              {!c.blocking && c.issues.length > 0 && <Tag style={{ marginLeft: 6, fontSize: 11 }}>提示</Tag>}
            </div>
            {c.issues.length > 0 && (
              <div style={{ marginTop: 4 }}>
                {c.issues.slice(0, 2).map((iss, i) => (
                  <Button
                    key={i}
                    size="small"
                    type="link"
                    icon={<ToolOutlined />}
                    style={{ padding: 0, marginTop: 2 }}
                    onClick={() => openFix(c.key, iss)}
                  >
                    修复 {iss.column}
                  </Button>
                ))}
                {c.issues.length > 2 && (
                  <div style={{ marginTop: 4 }}>
                    <Button size="small" type="link" onClick={() => {}}>
                      还有 {c.issues.length - 2} 个... 查看表格修复
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>

      {allFlatIssues.length > 0 && (
        <>
          <div style={{ marginBottom: 10, fontSize: 13, color: '#8c8c8c' }}>
            点击任意问题行展开：规则问题看受影响原始行与清洗结果；AI 补充问题看大白话结论、判断依据、涉及字段，并可点「查看明细数据」核对真实数据行。
          </div>
          <Table
            size="small"
            pagination={false}
            scroll={{ x: 1100 }}
            dataSource={allFlatIssues}
            rowKey={r => `${r.checkKey}-${r.column}-${r.type}`}
            expandable={{
              rowExpandable: (r: any) => (r.samples?.length || 0) > 0 || r.source === 'ai',
              expandedRowRender: (r: any) => r.source === 'ai' ? (
                <div style={{ padding: '6px 4px', lineHeight: 1.9 }}>
                  <div><b>大白话结论：</b>{r.plain_conclusion || r.message}</div>
                  <div><b>判断依据：</b>{r.basis || '请点「查看明细数据」核对真实行'}</div>
                  <div><b>涉及字段：</b>{(r.involved_columns?.length ? r.involved_columns : [r.column]).join('、')}</div>
                  <div><b>核对建议：</b>{r.check_suggestion || '打开明细，核对涉及字段的真实取值'}</div>
                  <div><b>AI 修复策略：</b>{r.repair_plan?.label || '先核对明细再决定'}
                    {r.repair_plan?.reason && <span style={{ color: '#8c8c8c' }}>（{r.repair_plan.reason}）</span>}
                  </div>
                  {r.repair && <div><b>已执行：</b>{r.repair.label}，改动 {r.repair.affected_rows} 行</div>}
                  <div style={{ marginTop: 8 }}>
                    {decisionTag(r.confirmation?.decision)}
                    <Button size="small" type="primary" ghost style={{ marginLeft: 8 }}
                            icon={<FileSearchOutlined />} onClick={() => { void openEvidence(r) }}>
                      查看明细数据
                    </Button>
                  </div>
                </div>
              ) : (
                <Table
                  size="small"
                  pagination={false}
                  style={{ margin: '4px 0' }}
                  dataSource={r.samples || []}
                  rowKey={(s: any) => `${r.checkKey}-${r.column}-${s.row}`}
                  columns={[
                    { title: '原始数据行', dataIndex: 'row', key: 'row', width: 90, render: (v: number) => <Text type="secondary">第 {v} 行</Text> },
                    { title: '清洗前的值', dataIndex: 'raw', key: 'raw', width: 160, render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code> },
                    { title: '对应的问题', dataIndex: 'problem', key: 'problem', width: 220 },
                    {
                      title: '清洗后结果',
                      key: 'fixed',
                      width: 220,
                      render: (_: any, s: any) => {
                        if (s.action === 'delete') return <Tag color="red">删除该行</Tag>
                        if (s.action === 'keep') return <Tag>保留（标记异常）</Tag>
                        if (s.action === 'mask') return <Tag color="blue">{s.fixed || '脱敏'}</Tag>
                        return s.fixed ? <span style={{ color: '#52c41a', fontWeight: 500 }}>{s.fixed}</span> : <Tag>修复</Tag>
                      },
                    },
                  ]}
                />
              ),
            }}
            columns={[
              { title: '校验项', dataIndex: 'checkLabel', key: 'checkLabel', width: 100 },
              {
                title: '来源',
                dataIndex: 'source',
                key: 'source',
                width: 60,
                render: (s) => s === 'ai' ? <Tag color="blue">AI</Tag> : <Tag>规则</Tag>,
              },
              { title: '字段', dataIndex: 'column', key: 'column', width: 130 },
              {
                title: '问题概述',
                dataIndex: 'message',
                key: 'message',
                width: 250,
                render: (v: string, r: any) => r.source === 'ai'
                  ? <Tooltip title={`AI 原始描述：${v}`}><span>{r.plain_conclusion || v}</span></Tooltip>
                  : <span>{v}</span>,
              },
              { title: '影响行数', dataIndex: 'row_count', key: 'row_count', width: 80, render: (v: number) => <Tag color="orange">{v}</Tag> },
              {
                title: '级别',
                key: 'level',
                width: 70,
                render: (_: any, r: any) => r.blocking ? <Tag color="red">阻断</Tag> : <Tag>提示</Tag>,
              },
              {
                title: '状态',
                key: 'fixStatus',
                width: 90,
                render: (_: any, r: any) =>
                  (state.fixedKeys.has(issueKey(r.checkKey, r.column)) || !!(r as any).repair)
                    ? <Tag icon={<CheckCircleOutlined />} color="success">已修复</Tag>
                    : <Tag color="orange">待修复</Tag>,
              },
              {
                title: '推荐处理方案',
                key: 'plan',
                width: 230,
                render: (_: any, r: any) => {
                  // Task #724：AI 问题没有自动清洗方案，旧下拉「忽略（AI 建议，需人工确认）」
                  // 让用户只能盲信或盲弃。这里直接给核对状态 + 可执行的下一步。
                  if (r.source === 'ai') {
                    const plan = r.repair_plan || {}
                    const done = !!r.repair
                    return (
                      <div>
                        {done
                          ? <Tag color="success">已按 AI 策略修复</Tag>
                          : decisionTag(r.confirmation?.decision)}
                        <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                          {done
                            ? `策略：${r.repair?.label || plan.label || '—'}，改动 ${r.repair?.affected_rows ?? 0} 行`
                            : `AI 修复策略：${plan.label || '先核对明细再决定'}`}
                        </div>
                        <Button size="small" type="link" style={{ paddingLeft: 0 }}
                                onClick={() => { void openEvidence(r) }}>
                          {done ? '查看修复结果' : '查看策略与明细数据'}
                        </Button>
                      </div>
                    )
                  }
                  const opts: RepairOption[] = r.repair_options || []
                  const cur = strategyOf(r.checkKey, r)
                  const curOpt = opts.find(o => o.strategy === cur)
                  // C2：质检发现（规则检测）且尚未采纳的行 → 显示「待采纳（推荐：xxx）」，不展示非策略值
                  const isDetected = r.source !== 'ai'
                  const notAdopted = !state.fixedKeys.has(issueKey(r.checkKey, r.column))
                  const recOpt = opts.find(o => o.recommended)
                    || opts.find(o => o.strategy !== 'ignore' && o.strategy !== 'drop')
                  const recLabel = recOpt ? (STRATEGY_LABEL_MAP[recOpt.strategy] || recOpt.label || recOpt.strategy) : ''
                  return (
                    <div>
                      {isDetected && notAdopted && (
                        <Tag color="gold" style={{ marginBottom: 2 }}>待采纳（推荐：{recLabel || '—'}）</Tag>
                      )}
                      <Select
                        size="small"
                        style={{ width: '100%' }}
                        value={cur || undefined}
                        placeholder="选择处理方案"
                        onChange={(v) => setStrategyMap(prev => ({
                          ...prev, [issueKey(r.checkKey, r.column)]: v
                        }))}
                        options={opts.map(o => ({
                          value: o.strategy,
                          label: o.recommended ? `${o.label}（推荐）` : o.label,
                        }))}
                      />
                      {curOpt?.description && (
                        <Tooltip title={curOpt.description}>
                          <div style={{
                            fontSize: 12, color: '#8c8c8c', marginTop: 2,
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {curOpt.description}
                          </div>
                        </Tooltip>
                      )}
                    </div>
                  )
                },
              },
              {
                title: '操作',
                key: 'action',
                width: 140,
                render: (_: any, r: any) => r.source === 'ai' ? (
                  <Button size="small" type="primary" ghost icon={<FileSearchOutlined />}
                          onClick={() => { void openEvidence(r) }}>
                    {r.repair ? '查看修复结果' : '查看明细数据'}
                  </Button>
                ) : (
                  <Button size="small" icon={<ToolOutlined />} onClick={() => openFix(r.checkKey, r)}>
                    修复
                  </Button>
                ),
              },
            ]}
          />
        </>
      )}

      {allFlatIssues.length === 0 && (
        <Empty description="未检测到数据质量问题" style={{ margin: '32px 0' }} />
      )}

      {/* B2/B3：清洗修复行级变更明细（before/after 快照）+ 蓝条自述 */}
      <Card
        size="small"
        style={{ marginTop: 16 }}
        title="清洗修改明细（行级 before / after）"
        extra={
          <Button
            size="small"
            type="link"
            onClick={() => {
              setChangeLogOpen(o => !o)
              if (!changeLogLoadedRef.current) {
                changeLogLoadedRef.current = true
                loadChangeLog()
              }
            }}
          >
            {changeLogOpen ? '收起' : `展开（${changeLog.length}）`}
          </Button>
        }
      >
        {changeLogOpen && (
          <>
            {/* B3 蓝条自述：说明每次修复都会落行级 before/after 明细，可审计回溯 */}
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="每次采纳修复方案后，系统会记录该字段的清洗前/后明细（空值数、去重数、极值等），可在此按「聚合」或「逐行」查看，便于审计与回溯。"
            />
            <Radio.Group
              value={changeView}
              onChange={e => setChangeView(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              size="small"
              style={{ marginBottom: 12 }}
            >
              <Radio value="agg">按字段聚合</Radio>
              <Radio value="row">逐行明细</Radio>
            </Radio.Group>
            {changeLogLoading && <div style={{ color: '#8c8c8c', fontSize: 13 }}>加载中…</div>}
            {!changeLogLoading && changeLog.length === 0 && (
              <Empty description="暂无清洗修改记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
            {!changeLogLoading && changeLog.length > 0 && changeView === 'agg' && (
              <Table
                size="small"
                pagination={false}
                dataSource={aggGroups}
                rowKey={(r: any) => `${r.field_name}__${r.strategy}`}
                columns={[
                  { title: '字段', dataIndex: 'field_name', key: 'field_name' },
                  { title: '修复策略', dataIndex: 'strategy', key: 'strategy', render: (v: string) => STRATEGY_LABEL_MAP[v] || v },
                  { title: '问题类型', dataIndex: 'issue_type', key: 'issue_type' },
                  { title: '修改次数', dataIndex: 'count', key: 'count', render: (v: number) => <Tag>{v}</Tag> },
                  { title: '影响行数', dataIndex: 'affected', key: 'affected', render: (v: number) => <Tag color="orange">{v}</Tag> },
                  { title: '清洗前 → 后', key: 'delta', render: (_: any, r: any) => describeStats(r.before, r.after) },
                ]}
              />
            )}
            {!changeLogLoading && changeLog.length > 0 && changeView === 'row' && (
              <Table
                size="small"
                pagination={{ pageSize: 10 }}
                dataSource={changeLog}
                rowKey={(r: any) => r.id}
                columns={[
                  { title: '字段', dataIndex: 'field_name', key: 'field_name', width: 120 },
                  { title: '问题类型', dataIndex: 'issue_type', key: 'issue_type', width: 90 },
                  { title: '策略', dataIndex: 'strategy', key: 'strategy', width: 120, render: (v: string) => STRATEGY_LABEL_MAP[v] || v },
                  { title: '影响行数', dataIndex: 'affected_rows', key: 'affected_rows', width: 80, render: (v: number) => <Tag color="orange">{v}</Tag> },
                  { title: '清洗前', dataIndex: 'before_value', key: 'before_value', width: 160, render: (v: any) => v ? `空值${v.null_count ?? '-'} 去重${v.distinct_count ?? '-'}` : '-' },
                  { title: '清洗后', dataIndex: 'after_value', key: 'after_value', width: 160, render: (v: any) => v ? `空值${v.null_count ?? '-'} 去重${v.distinct_count ?? '-'}` : '-' },
                  { title: '修改时间', dataIndex: 'created_at', key: 'created_at', width: 160 },
                ]}
              />
            )}
          </>
        )}
      </Card>


      <Divider />
      {/* 问题3：修复完成→看板生成的过渡态，内联"进行中"反馈 */}
      {generating && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="已修复完成，正在生成看板…"
        />
      )}
      {/* ISS-063：批量修复内联状态条（超时/取消/重试/成功与部分失败均内联可见，不再只靠 message.loading） */}
      {(applyingPlan || applyError || applyResult) && (
        <div style={{ marginBottom: 12 }}>
          {applyingPlan && (
            <Alert
              type="info"
              showIcon
              message={
                <span>
                  正在按推荐方案批量修复（{planMode === 'blocking' ? '仅必拦项' : '全部问题'}）… 已用时 {applyElapsed}s
                </span>
              }
              action={
                <Button size="small" onClick={() => planAbortRef.current?.abort()}>
                  取消
                </Button>
              }
            />
          )}
          {!applyingPlan && applyError && (
            <Alert
              type="error"
              showIcon
              message={applyError}
              action={
                <Button size="small" danger onClick={() => applyRecommendedPlan(planMode === 'blocking')}>
                  重试修复
                </Button>
              }
            />
          )}
          {!applyingPlan && applyResult && (
            applyResult.failed > 0 ? (
              <Alert type="warning" showIcon message={`已修复 ${applyResult.success} 项，${applyResult.failed} 项失败（可逐条处理）`} />
            ) : (
              <Alert type="success" showIcon message={`已修复全部 ${applyResult.success} 项问题`} />
            )
          )}
        </div>
      )}
      {/* 问题3 底部按钮区：左"忽略质检生成看板"（无阻断才亮），右"一键修复生成看板"（修复完自动进生成） */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: '#8c8c8c', fontSize: 13 }}>
          质检进度：{passCount}/{state.checks.length} 通过
          {hasBlockingErrors && ` · 存在 ${blockingIssueCount} 个必拦项`}
        </span>
        <Space size={12}>
          <Button
            size="large"
            loading={generating}
            disabled={hasBlockingErrors || checking || applyingPlan || generating}
            onClick={() => { onProceed?.() }}
          >
            忽略质检生成看板
          </Button>
          {totalIssues > 0 && (
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              loading={(applyingPlan && planMode === 'all') || generating}
              disabled={checking || (applyingPlan && planMode !== 'all') || generating}
              onClick={() => { setPlanMode('all'); applyRecommendedPlan(false, true) }}
            >
              一键修复生成看板（{totalIssues}项）
            </Button>
          )}
        </Space>
      </div>

      {/* Task #724：AI 补充检测证据链 / 真实明细下钻弹窗 */}
      <Modal
        title={`查看明细数据 — ${evidenceModal.issue?.column || ''}`}
        open={evidenceModal.open}
        onCancel={() => setEvidenceModal({ open: false, issue: null })}
        width={980}
        footer={[
          <Button key="close" onClick={() => setEvidenceModal({ open: false, issue: null })}>关闭</Button>,
          <Button key="pending" loading={confirming} disabled={!evidenceData || confirming}
                  onClick={() => { void confirmAiIssue('pending') }}>撤销结论</Button>,
          <Button key="ignored" loading={confirming} disabled={!evidenceData || confirming}
                  onClick={() => { void confirmAiIssue('ignored') }}>标记无需处理</Button>,
          <Button key="confirmed" loading={confirming} disabled={!evidenceData || confirming}
                  onClick={() => { void confirmAiIssue('confirmed') }}>确认问题属实</Button>,
          <Button key="repair" type="primary" icon={<ThunderboltOutlined />} loading={repairing}
                  disabled={!evidenceData?.can_auto_repair
                    || evidenceData?.confirmation?.decision !== 'confirmed' || repairing}
                  onClick={() => { void applyAiRepair() }}>按 AI 建议修复</Button>,
        ]}
      >
        {evidenceLoading && <div style={{ padding: 48, textAlign: 'center' }}><Spin tip="正在读取真实明细数据…" /></div>}
        {evidenceError && <Alert type="error" showIcon message="明细数据读取失败" description={evidenceError} />}
        {evidenceData && (
          <>
            <Alert
              type="info" showIcon style={{ marginBottom: 12 }}
              message={evidenceData.plain_conclusion || 'AI 补充检测提示'}
              description={evidenceData.basis || '请直接核对下方真实明细数据'}
            />
            <div style={{ marginBottom: 12, lineHeight: 2 }}>
              <div><b>涉及字段：</b>{(evidenceData.involved_columns || []).map((c: string) => <Tag key={c}>{c}</Tag>)}</div>
              <div><b>核对建议：</b>{evidenceData.check_suggestion || '打开明细，核对涉及字段的真实取值'}</div>
              <div><b>当前核对状态：</b>{decisionTag(evidenceData.confirmation?.decision)}</div>
            </div>
            {/* #34：AI 修复策略卡片 —— 确认属实后有明确可执行的下一步，不再卡在「待修复」 */}
            <Alert
              type={evidenceData.repair ? 'success' : 'info'} showIcon style={{ marginBottom: 12 }}
              message={evidenceData.repair
                ? `已修复：${evidenceData.repair.label || evidenceData.repair_plan?.label || ''}（改动 ${evidenceData.repair.affected_rows ?? 0} 行）`
                : `AI 修复建议：${evidenceData.repair_plan?.label || '先查看明细再决定'}`}
              description={evidenceData.repair
                ? '数据写在清洗层，原始层未动；可在下方「清洗修改明细」查看逐行前后对比，或点质检页「重置」回滚。'
                : `${evidenceData.repair_plan?.reason || 'AI 未给出具体依据，请先核对下方真实数据行。'} 风险提示：${evidenceData.repair_plan?.risk || '执行前请确认这几行确属异常。'}`}
            />
            {!evidenceData.repair && (
              <div style={{ marginBottom: 12, lineHeight: 2.2 }}>
                <div>
                  <b>改选修复策略：</b>
                  <Select
                    size="small" style={{ width: 320, marginLeft: 8 }}
                    value={repairStrategy || evidenceData.repair_plan?.strategy || undefined}
                    onChange={(v) => setRepairStrategy(v)}
                    options={Object.entries(evidenceData.repair_strategies || {}).map(([k, v]: [string, any]) => ({
                      value: k, label: v?.label || k,
                    }))}
                  />
                </div>
                {(repairStrategy || evidenceData.repair_plan?.strategy) === 'replace_with_constant' && (
                  <div><b>替换成：</b>
                    <input
                      style={{ marginLeft: 8, padding: '4px 8px', border: '1px solid #d9d9d9', borderRadius: 4 }}
                      value={repairTargetValue}
                      placeholder="填写核对后的正确值"
                      onChange={(e) => setRepairTargetValue(e.target.value)}
                    />
                  </div>
                )}
                <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                  AI 只给建议、不直接改数；执行时只修改下方定位到的 {evidenceData.total_matched} 行，写清洗层并留回退点。
                </div>
                {repairError && <Alert type="error" showIcon message="修复未执行" description={repairError} />}
              </div>
            )}
            <Divider style={{ margin: '10px 0' }}>真实数据明细（直接查数据表，共 {evidenceData.total_matched} 行）</Divider>
            <Alert
              type={evidenceData.locator === 'filter' ? 'success' : 'warning'} showIcon
              style={{ marginBottom: 8 }} message={evidenceData.sql_note}
            />
            <Table
              size="small" pagination={false} scroll={{ x: 900 }}
              dataSource={evidenceData.rows || []}
              rowKey={(r: any) => `d-${r._row_no}`}
              columns={[
                { title: '行号', dataIndex: '_row_no', key: '_row_no', width: 80, render: (v: number) => `第 ${v} 行` },
                ...(evidenceData.columns || []).map((c: string) => ({
                  title: c, dataIndex: c, key: c,
                  render: (v: any) => v === null ? <Tag>空值</Tag> : String(v ?? ''),
                })),
              ]}
              locale={{ emptyText: '没有匹配到数据行' }}
            />
            <Divider style={{ margin: '16px 0 10px' }}>AI 判断依据样本（AI 当时看到的前 8 行）</Divider>
            <Table
              size="small" pagination={false} scroll={{ x: 900 }}
              dataSource={evidenceData.ai_seen_rows || []}
              rowKey={(r: any) => `s-${r._row_no}`}
              onRow={(r: any) => ({
                style: (evidenceData.highlight_rows || []).includes(r._row_no)
                  ? { background: 'rgba(250, 173, 20, 0.14)' } : undefined,
              })}
              columns={[
                { title: '样本行号', dataIndex: '_row_no', key: '_row_no', width: 90, render: (v: number) => `第 ${v} 行` },
                ...((evidenceData.sample_columns && evidenceData.sample_columns.length
                  ? evidenceData.sample_columns
                  : Object.keys((evidenceData.ai_seen_rows || [])[0] || {}).filter((k: string) => k !== '_row_no')
                ).map((c: string) => ({
                  title: c, dataIndex: c, key: c,
                  render: (v: any) => v === null ? <Tag>空值</Tag> : String(v ?? ''),
                }))),
              ]}
              locale={{ emptyText: '本次没有留存 AI 样本' }}
            />
          </>
        )}
      </Modal>

      {/* 修复弹窗 - 显示所有可选修复方案 */}
      <Modal
        title={`修复 - ${fixCheck?.label || ''} - ${fixModal.issue?.column}`}
        open={fixModal.open}
        onCancel={() => setFixModal({ open: false, checkKey: '', issue: null })}
        footer={[
          <Button key="cancel" onClick={() => setFixModal({ open: false, checkKey: '', issue: null })}>
            取消
          </Button>,
          <Button key="apply" type="primary" icon={<ThunderboltOutlined />} loading={fixing} disabled={fixing} onClick={applyFix}>
            应用修复方案
          </Button>,
        ]}
        width={560}
      >
        {fixModal.issue && (
          <>
            <Alert
              type="info"
              showIcon
              message={fixModal.issue.message}
              description={fixModal.issue.detail}
              style={{ marginBottom: 16 }}
            />
            <Divider style={{ margin: '12px 0' }} />
            <div style={{ marginBottom: 12 }}>
              <b>请选择修复方案：</b>
            </div>
            <Radio.Group
              value={selectedStrategy}
              onChange={e => setSelectedStrategy(e.target.value)}
              style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
            >
              {fixModal.issue.repair_options.map(opt => (
                <Radio key={opt.strategy} value={opt.strategy}>
                  <div>
                    <div>{opt.label}</div>
                    <div style={{ fontSize: 12, color: '#666', marginTop: 2 }}>
                      {opt.description}
                    </div>
                  </div>
                </Radio>
              ))}
            </Radio.Group>
            {selectedStrategy === 'fill_constant' && (
              <>
                <Divider style={{ margin: '16px 0 12px' }} />
                <Input
                  placeholder="请输入填充值"
                  value={customValue}
                  onChange={e => setCustomValue(e.target.value)}
                />
              </>
            )}
          </>
        )}
      </Modal>

      {/* ISS-064：重置（撤销清洗）二次确认弹窗 */}
      <Modal
        title="重置数据（撤销清洗）"
        open={resetModalOpen}
        onCancel={() => setResetModalOpen(false)}
        okText="确定重置"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: resetting }}
        onOk={resetAll}
      >
        <p>此操作将<strong>删除清洗层并撤销所有已采纳的修复</strong>，数据回滚到原始上传状态。确定要重置吗？</p>
      </Modal>
    </Card>
    </SkillPanel>
  )
}