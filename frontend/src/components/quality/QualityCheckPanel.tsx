import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, Button, Tag, Table, Modal, Radio, Input, Space, Divider, Alert, message, Typography, Empty, Select, Tooltip } from 'antd'
import {
  CheckCircleOutlined, WarningOutlined, CloseCircleOutlined,
  ToolOutlined, ReloadOutlined, ThunderboltOutlined, LoadingOutlined,
} from '@ant-design/icons'
// Phase 5：SkillPanel 薄壳收口（展示本面板由哪些后端 skill 驱动，暗色自动继承）
import SkillPanel from '../skills/SkillPanel'
import { authHeaders } from '../../utils/request'

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

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

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

export default function QualityCheckPanel({
  fileId, fileName, datasetId, onProceed, onStatusChange, autoCheck = true,
}: QualityCheckPanelProps) {
  const [state, setState] = useState<CheckState>(() => getStateForFile(fileId, groupIssuesByType([])))
  const [checking, setChecking] = useState(false)
  const [checked, setChecked] = useState(false)
  const [aiStatus, setAiStatus] = useState<'idle' | 'running' | 'done' | 'failed'>('idle')
  const [applyingPlan, setApplyingPlan] = useState(false)
  // 当前批量修复模式（用于分别控制两个按钮的 loading 态）：'blocking' | 'all'
  const [planMode, setPlanMode] = useState<'blocking' | 'all'>('all')

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
  const pollAiResult = useCallback((dsId: string) => {
    if (aiIntervalRef.current) clearInterval(aiIntervalRef.current)
    let attempts = 0
    const MAX_ATTEMPTS = 45  // ~90秒后停止轮询
    const timer = setInterval(async () => {
      attempts++
      try {
        // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /quality/*，ISS-025 端点已加鉴权，前端必须带 token
        const res = await fetch(`${API_BASE}/quality/check/ai/${dsId}`, { headers: authHeaders() })
        const data = await res.json()
        if (data.status === 'done') {
          clearInterval(timer)
          aiIntervalRef.current = null
          setAiStatus('done')
          const issues = (data.issues || []) as ApiQualityIssue[]
          mergeAiResult(issues)
          if (data.ai_issues_count > 0) {
            message.info({ content: `质检完成：规则结果已显示，AI 补充发现 ${data.ai_issues_count} 个潜在问题`, key: 'qc' })
          }
        } else if (data.status === 'failed') {
          clearInterval(timer)
          aiIntervalRef.current = null
          setAiStatus('failed')
          message.warning(`AI补充检测暂不可用：${data.error || '未知原因'}（规则检测结果不受影响）`)
        }
        // running/pending：继续轮询
      } catch (e) {
        // 瞬态请求错误忽略，继续轮询
      }
      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(timer)
        aiIntervalRef.current = null
        setAiStatus(s => (s === 'idle' || s === 'running') ? 'failed' : s)
      }
    }, 2000)
    aiIntervalRef.current = timer
  }, [mergeAiResult])
  const [fixModal, setFixModal] = useState<{
    open: boolean
    checkKey: string
    issue: ApiQualityIssue | null
  }>({ open: false, checkKey: '', issue: null })
  const [selectedStrategy, setSelectedStrategy] = useState('')
  const [customValue, setCustomValue] = useState('')
  const [fixing, setFixing] = useState(false)
  
  // 切换文件时同步质检状态，并清理上一文件的AI轮询
  useEffect(() => {
    if (aiIntervalRef.current) {
      clearInterval(aiIntervalRef.current)
      aiIntervalRef.current = null
    }
    setAiStatus('idle')
    const existing = getStateForFile(fileId, groupIssuesByType([]))
    setState(existing)
  }, [fileId])
  
  // 一次性守卫：同一 datasetId 只自动处理一次，避免切 tab / StrictMode 重复触发
  const autoHandledRef = useRef<string>('')
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
    // 静默模式不弹 toast；非静默也只给 8 秒兜底时长，避免异常路径下永久卡住
    if (!silent) {
      message.loading({ content: '正在进行规则质检（秒级），AI补充检测后台进行中...', key: 'qc', duration: 8 })
    }
    // 规则检测很快，仅保留45秒兜底超时，避免按钮卡在loading
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 45000)
    try {
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /quality/*，ISS-025 端点已加鉴权，前端必须带 token
      const response = await fetch(`${API_BASE}/quality/check`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: datasetId }),
        signal: ctrl.signal,
      })
      const data = await response.json()

      if (!response.ok) {
        if (!silent) message.destroy('qc')
        message.error(data.detail?.message || '质检失败')
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

      if (!silent) {
        message.destroy('qc')
        message.success(`规则质检完成（${fileName || fileId}），AI补充检测后台进行中`)
      }
      // 启动后台轮询，AI结果就绪后自动合并进面板
      pollAiResult(datasetId)
      return grouped
    } catch (error: any) {
      if (!silent) message.destroy('qc')
      if (error?.name === 'AbortError') {
        message.error('质检超时，请重试')
      } else {
        message.error('质检请求失败')
      }
      setAiStatus('failed')
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
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 GET /quality/{id}/issues，已带 authHeaders()
      const res = await fetch(`${API_BASE}/quality/${datasetId}/issues`, { headers: authHeaders() })
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

  // 自动质检：只对「新上传」的数据集跑一次；恢复的历史数据集直接读已存结果（不重跑、不弹 toast）
  useEffect(() => {
    if (!datasetId) return
    if (autoHandledRef.current === datasetId) return
    autoHandledRef.current = datasetId

    if (autoCheck === false) {
      loadExisting().then(n => {
        // 后端没有任何已存记录（例如修复上线前的数据集）→ 静默兜底跑一次
        if (n === null) runCheck({ silent: true })
      })
      return
    }

    const timer = setTimeout(() => {
      runCheck()
    }, 500)
    return () => clearTimeout(timer)
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
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /quality/*，ISS-025 端点已加鉴权，前端必须带 token
      const response = await fetch(`${API_BASE}/quality/fix`, {
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
  }

  // 一键采纳推荐方案 — 对齐 B 的"推荐清洗计划"交互：后端已为每类问题标记 recommended 策略，
  // 这里汇总所有规则类问题生成推荐计划，批量调 /quality/fix-batch，完成后自动重跑质检刷新结果。
  // 2026-09-18：支持 onlyBlocking —— 对齐原型底部"仅处理必拦项，继续"，只批量修复阻断类问题。
  const applyRecommendedPlan = useCallback(async (onlyBlocking: boolean = false) => {
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
    setApplyingPlan(true)
    message.loading({ content: `正在按推荐方案批量修复 ${plan.length} 项...`, key: 'plan', duration: 0 })
    try {
      // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /quality/*，ISS-025 端点已加鉴权，前端必须带 token
      const resp = await fetch(`${API_BASE}/quality/fix-batch`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: datasetId, items: plan }),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        message.destroy('plan')
        message.error(data.detail?.message || '批量修复失败，请重试或逐条修复')
        return
      }
      message.destroy('plan')
      if (data.failed > 0) {
        message.warning(`已修复 ${data.success} 项，${data.failed} 项失败（可逐条处理）`)
      } else {
        message.success(`已按推荐方案修复 ${data.success} 项，正在重新质检...`)
      }
      // 重新质检：拿到最新结果，判断是否可以自动进入看板生成
      const newChecks = await runCheck()
      if (newChecks) {
        const remainBlocking = newChecks.some(c => c.blocking && c.status === 'fail')
        const remainWarn = newChecks.reduce((s, c) => s + c.issues.length, 0)
        if (!remainBlocking) {
          // 无阻断项 → 自动流转到看板生成（对齐方案B"一键采纳推荐方案→继续"）
          message.success(
            remainWarn > 0
              ? `质检通过（无阻断项），剩余 ${remainWarn} 个非阻断提示已自动保留，正在进入看板生成...`
              : '质检全部通过，正在进入看板生成...'
          )
          setTimeout(() => { onProceed?.() }, 700)
        } else {
          message.warning('仍有阻断性问题未修复，请在下方表格逐条处理后继续')
        }
      }
    } catch (e) {
      message.destroy('plan')
      message.error('批量修复请求失败（网络异常），请重试')
    } finally {
      setApplyingPlan(false)
    }
  }, [datasetId, checking, runCheck, strategyMap, onProceed])

  // 重置 — 清除所有修复记录
  const resetAll = () => {
    const newState: CheckState = {
      checks: groupIssuesByType([]),
      fixedKeys: new Set(),
    }
    updateState(newState)
    message.info('已重置所有质检状态')
  }
  
  const { Text } = Typography
  const fixCheck = state.checks.find(c => c.key === fixModal.checkKey)
  
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
          <Button size="small" onClick={resetAll}>重置</Button>
          <Button icon={<ReloadOutlined />} loading={checking} onClick={() => runCheck()}>重新质检</Button>
        </Space>
      }
      style={{ marginTop: 0 }}
    >
      {(aiStatus === 'running' || aiStatus === 'idle') && checked && (
        <Alert
          type="info"
          icon={<LoadingOutlined spin />}
          showIcon
          message="规则检测已完成；AI补充检测正在后台进行，结果就绪后会自动补充到下方"
          style={{ marginBottom: 16 }}
        />
      )}
      {aiStatus === 'failed' && (
        <Alert
          type="warning"
          showIcon
          message="AI补充检测暂不可用，当前显示为规则检测结果（阻断性判定不受影响）"
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
            点击任意问题行展开，可见受影响的原始数据行、清洗前的值与清洗后结果。
          </div>
          <Table
            size="small"
            pagination={false}
            scroll={{ x: 1100 }}
            dataSource={allFlatIssues}
            rowKey={r => `${r.checkKey}-${r.column}-${r.type}`}
            expandable={{
              rowExpandable: (r: any) => (r.samples?.length || 0) > 0,
              expandedRowRender: (r: any) => (
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
              { title: '问题概述', dataIndex: 'message', key: 'message', width: 230, ellipsis: true },
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
                  state.fixedKeys.has(issueKey(r.checkKey, r.column))
                    ? <Tag icon={<CheckCircleOutlined />} color="success">已修复</Tag>
                    : <Tag color="orange">待修复</Tag>,
              },
              {
                title: '推荐处理方案',
                key: 'plan',
                width: 230,
                render: (_: any, r: any) => {
                  const opts: RepairOption[] = r.repair_options || []
                  const cur = strategyOf(r.checkKey, r)
                  const curOpt = opts.find(o => o.strategy === cur)
                  return (
                    <div>
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
                width: 90,
                render: (_: any, r: any) => (
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

      <Divider />
      {/* 底部按钮区（2026-09-18 对齐原型）：左"仅处理必拦项，继续"，右"一键 AI 修复全部问题（N项）→" */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: '#8c8c8c', fontSize: 13 }}>
          质检进度：{passCount}/{state.checks.length} 通过
          {hasBlockingErrors && ` · 存在 ${blockingIssueCount} 个必拦项`}
        </span>
        <Space size={12}>
          <Button
            size="large"
            loading={applyingPlan && planMode === 'blocking'}
            disabled={checking || (applyingPlan && planMode !== 'blocking')}
            onClick={() => {
              if (hasBlockingErrors) {
                setPlanMode('blocking')
                applyRecommendedPlan(true)
              } else {
                onProceed?.()
              }
            }}
          >
            {hasBlockingErrors ? '仅处理必拦项，继续' : '生成看板'}
          </Button>
          {totalIssues > 0 && (
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              loading={applyingPlan && planMode === 'all'}
              disabled={checking || (applyingPlan && planMode !== 'all')}
              onClick={() => { setPlanMode('all'); applyRecommendedPlan(false) }}
            >
              一键修复全部问题（{totalIssues}项） →
            </Button>
          )}
        </Space>
      </div>

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
    </Card>
    </SkillPanel>
  )
}