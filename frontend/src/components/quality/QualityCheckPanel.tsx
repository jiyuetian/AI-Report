import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, Button, Tag, Table, Modal, Radio, Input, Space, Divider, Alert, message, Typography, Empty } from 'antd'
import {
  CheckCircleOutlined, WarningOutlined, CloseCircleOutlined,
  ToolOutlined, ArrowRightOutlined, ReloadOutlined, ThunderboltOutlined, LoadingOutlined,
} from '@ant-design/icons'

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
}

// 单个修复方案
export interface RepairOption {
  strategy: string
  label: string
  description: string
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
  'ai': 'AI补充检测',
}

interface QualityCheckPanelProps {
  fileId: string
  fileName?: string
  datasetId?: string
  onProceed?: () => void
  onStatusChange?: (status: QualityCheckStatus) => void
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
  
  // 固定顺序：空值、格式、唯一性、范围、逻辑、码值、AI检测
  const order = ['null', 'format', 'unique', 'range', 'logic', 'code', 'ai']
  
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

export default function QualityCheckPanel({ fileId, fileName, datasetId, onProceed, onStatusChange }: QualityCheckPanelProps) {
  const [state, setState] = useState<CheckState>(() => getStateForFile(fileId, groupIssuesByType([])))
  const [checking, setChecking] = useState(false)
  const [checked, setChecked] = useState(false)
  const [aiStatus, setAiStatus] = useState<'idle' | 'running' | 'done' | 'failed'>('idle')

  // 供轮询回调读取最新状态，避免闭包拿到过期值
  const stateRef = useRef(state)
  useEffect(() => { stateRef.current = state }, [state])
  const aiIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
        const res = await fetch(`${API_BASE}/quality/check/ai/${dsId}`)
        const data = await res.json()
        if (data.status === 'done') {
          clearInterval(timer)
          aiIntervalRef.current = null
          setAiStatus('done')
          const issues = (data.issues || []) as ApiQualityIssue[]
          mergeAiResult(issues)
          if (data.ai_issues_count > 0) {
            message.info(`AI补充检测完成，发现 ${data.ai_issues_count} 个潜在问题`)
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
  
  // 当datasetId就绪时自动执行质检
  useEffect(() => {
    if (datasetId) {
      const timer = setTimeout(() => {
        runCheck()
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [datasetId])
  
  // 统计阻断项
  const blockingChecks = state.checks.filter(c => c.blocking)
  const hasBlockingErrors = blockingChecks.some(c => c.status === 'fail')
  const totalIssues = state.checks.reduce((sum, c) => sum + c.issues.length, 0)
  const passCount = state.checks.filter(c => c.status === 'pass').length
  
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
  const runCheck = useCallback(async () => {
    if (!datasetId) {
      message.warning('数据集未创建，请等待预览完成')
      return
    }
    setChecking(true)
    setAiStatus('running')
    message.loading({ content: '正在进行规则质检（秒级），AI补充检测后台进行中...', key: 'qc', duration: 0 })
    // 规则检测很快，仅保留45秒兜底超时，避免按钮卡在loading
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 45000)
    try {
      const response = await fetch(`${API_BASE}/quality/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: datasetId }),
        signal: ctrl.signal,
      })
      const data = await response.json()
      
      if (!response.ok) {
        message.destroy('qc')
        message.error(data.detail?.message || '质检失败')
        setAiStatus('failed')
        return
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
      
      message.destroy('qc')
      message.success(`规则质检完成（${fileName || fileId}），AI补充检测后台进行中`)
      // 启动后台轮询，AI结果就绪后自动合并进面板
      pollAiResult(datasetId)
    } catch (error: any) {
      message.destroy('qc')
      if (error?.name === 'AbortError') {
        message.error('质检超时，请重试')
      } else {
        message.error('质检请求失败')
      }
      setAiStatus('failed')
    } finally {
      clearTimeout(timer)
      setChecking(false)
    }
  }, [fileId, fileName, datasetId, pollAiResult])
  
  const openFix = (checkKey: string, issue: ApiQualityIssue) => {
    setFixModal({ open: true, checkKey, issue })
    // 默认选第一个修复方案
    setSelectedStrategy(issue.repair_options[0]?.strategy || '')
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
      const response = await fetch(`${API_BASE}/quality/fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
      extra={<Button icon={<ReloadOutlined />} loading={checking} onClick={runCheck}>重新质检</Button>}
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
        <Table
          size="small"
          pagination={false}
          dataSource={allFlatIssues}
          rowKey={r => `${r.checkKey}-${r.column}-${r.type}`}
          columns={[
            { title: '校验项', dataIndex: 'checkLabel', key: 'checkLabel', width: 100 },
            {
              title: '来源',
              dataIndex: 'source',
              key: 'source',
              width: 60,
              render: (s) => s === 'ai' ? <Tag color="blue">AI</Tag> : <Tag>规则</Tag>,
            },
            { title: '字段', dataIndex: 'column', key: 'column', width: 120 },
            { title: '问题', dataIndex: 'message', key: 'message', width: 180 },
            { title: '数量', dataIndex: 'row_count', key: 'row_count', width: 60, render: (v: number) => <Tag color="orange">{v}</Tag> },
            {
              title: '级别',
              key: 'level',
              width: 70,
              render: (_: any, r: any) => r.blocking ? <Tag color="red">阻断</Tag> : <Tag>提示</Tag>,
            },
            {
              title: '操作',
              key: 'action',
              width: 80,
              render: (_: any, r: any) => (
                <Button size="small" icon={<ToolOutlined />} onClick={() => openFix(r.checkKey, r)}>
                  修复
                </Button>
              ),
            },
          ]}
        />
      )}

      {allFlatIssues.length === 0 && (
        <Empty description="未检测到数据质量问题" style={{ margin: '32px 0' }} />
      )}

      <Divider />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: '#8c8c8c', fontSize: 13 }}>
          质检进度：{passCount}/{state.checks.length} 通过
          {hasBlockingErrors && ' · 存在阻断项，需修复后继续'}
        </span>
        <Space>
          <Button onClick={resetAll}>重置</Button>
          <Button
            type="primary"
            size="large"
            icon={<ArrowRightOutlined />}
            disabled={hasBlockingErrors}
            onClick={onProceed}
          >
            {hasBlockingErrors ? '需先修复阻断项' : '继续生成看板'}
          </Button>
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
  )
}