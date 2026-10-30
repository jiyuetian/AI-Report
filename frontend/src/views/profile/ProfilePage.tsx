import React, { useCallback, useEffect, useState } from 'react'
import {
  Card,
  Collapse,
  Tag,
  Button,
  Input,
  Space,
  Table,
  Typography,
  Empty,
  Spin,
  Tabs,
  message,
  Tooltip,
} from 'antd'
import {
  LikeOutlined,
  DislikeOutlined,
  UserOutlined,
  ClockCircleOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { http } from '@/utils/request'

const { Text, Paragraph } = Typography

interface RunSummary {
  run_id: string
  dataset_id?: string | null
  dashboard_id?: string | null
  user_id?: string | null
  overall_status?: string | null
  current_stage?: string | null
  stages?: Record<string, string>
  final_score?: number | null
  passed?: number | null
  started_at?: string | null
  completed_at?: string | null
}

interface ReasoningRecord {
  step?: string
  input_summary?: string | null
  ai_decision?: string | null
  ai_reason?: string | null
  rules_applied?: string[] | null
  fallback_used?: boolean | null
  output_ref?: any
}

interface TraceItem {
  id: string
  run_id: string
  stage: string
  stage_name?: string | null
  stage_status?: string | null
  stage_output?: any
  reasoning?: ReasoningRecord | ReasoningRecord[] | null
  started_at?: string | null
  completed_at?: string | null
}

function normReasoning(r: any): ReasoningRecord[] {
  if (!r) return []
  if (Array.isArray(r)) return r.filter((x) => x && typeof x === 'object')
  if (typeof r === 'object') return [r]
  return []
}

function ReasoningBlock({ reasoning }: { reasoning: any }) {
  const recs = normReasoning(reasoning)
  if (recs.length === 0) {
    return <Text type="secondary">（本步未记录推理日志）</Text>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {recs.map((rec, i) => (
        <div
          key={i}
          style={{
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            padding: 12,
            background: '#fafafa',
          }}
        >
          <div style={{ marginBottom: 6 }}>
            <Tag color="blue">{rec.step || 'STEP'}</Tag>
            {rec.fallback_used ? (
              <Tag color="orange">触发兜底</Tag>
            ) : (
              <Tag color="default">未触发兜底</Tag>
            )}
          </div>
          <Field label="输入摘要" value={rec.input_summary} />
          <Field label="处置决定" value={rec.ai_decision} />
          <Field label="决定依据 / 原因" value={rec.ai_reason} />
          <Field
            label="应用规则"
            value={
              rec.rules_applied && rec.rules_applied.length
                ? rec.rules_applied.join('、')
                : '—'
            }
          />
          <Field
            label="输出指代"
            value={rec.output_ref != null ? JSON.stringify(rec.output_ref) : '—'}
          />
        </div>
      ))}
    </div>
  )
}

function Field({ label, value }: { label: string; value?: any }) {
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 13, lineHeight: '20px' }}>
      <Text type="secondary" style={{ flex: '0 0 96px' }}>
        {label}
      </Text>
      <div style={{ flex: 1, wordBreak: 'break-word' }}>
        {value == null || value === '' ? (
          <Text type="secondary">—</Text>
        ) : (
          <span>{String(value)}</span>
        )}
      </div>
    </div>
  )
}

function StageOutput({ output }: { output: any }) {
  if (output == null) return <Text type="secondary">（无输出）</Text>
  const s = JSON.stringify(output, null, 2)
  return (
    <pre
      style={{
        maxHeight: 260,
        overflow: 'auto',
        background: '#0d1117',
        color: '#c9d1d9',
        padding: 12,
        borderRadius: 8,
        fontSize: 12,
        margin: 0,
      }}
    >
      {s}
    </pre>
  )
}

export default function ProfilePage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loadingRuns, setLoadingRuns] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [trace, setTrace] = useState<{ summary: any; traces: TraceItem[] } | null>(null)
  const [loadingTrace, setLoadingTrace] = useState(false)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const loadRuns = useCallback(async () => {
    setLoadingRuns(true)
    try {
      const res = await http.get<{ success: boolean; runs: RunSummary[] }>('/brain/runs', {
        limit: 100,
      })
      setRuns(res?.runs ?? [])
    } catch (e: any) {
      message.error(e?.message || '加载运行记录失败')
    } finally {
      setLoadingRuns(false)
    }
  }, [])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  const openRun = useCallback(
    async (runId: string) => {
      setSelectedRunId(runId)
      setLoadingTrace(true)
      setTrace(null)
      try {
        const res = await http.get<{
          success: boolean
          summary: any
          traces: TraceItem[]
        }>(`/brain/runs/${runId}/traces`)
        setTrace({ summary: res?.summary, traces: res?.traces ?? [] })
      } catch (e: any) {
        if (e?.status === 403) {
          message.error('无权查看该运行记录（仅可查看本人运行）')
        } else {
          message.error(e?.message || '加载运行详情失败')
        }
      } finally {
        setLoadingTrace(false)
      }
    },
    [],
  )

  const submitFeedback = useCallback(
    async (feedback: 'like' | 'dislike') => {
      if (!selectedRunId) return
      setSubmitting(true)
      try {
        await http.post(`/brain/runs/${selectedRunId}/feedback`, {
          feedback,
          note: note || undefined,
        })
        message.success(feedback === 'like' ? '已点赞 👍' : '已点踩 👎，感谢反馈')
      } catch (e: any) {
        message.error(e?.message || '提交反馈失败')
      } finally {
        setSubmitting(false)
      }
    },
    [selectedRunId, note],
  )

  const runColumns: ColumnsType<RunSummary> = [
    {
      title: '运行ID',
      dataIndex: 'run_id',
      key: 'run_id',
      width: 110,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v.slice(0, 8)}…</Text>,
    },
    {
      title: '数据集',
      dataIndex: 'dataset_id',
      key: 'dataset_id',
      width: 120,
      ellipsis: true,
      render: (v: string | null) => (v ? <Text style={{ fontSize: 12 }}>{v.slice(0, 8)}…</Text> : '-'),
    },
    {
      title: '阶段进度',
      key: 'stages',
      width: 220,
      render: (_: any, r: RunSummary) => {
        const stages = r.stages || {}
        const order = ['S1', 'S2', 'S3', 'S4', 'S5']
        return (
          <Space size={2} wrap>
            {order.map((s) => {
              const st = stages[s]
              const color =
                st === 'success' ? 'green' : st === 'failed' ? 'red' : 'default'
              return (
                <Tag key={s} color={color} style={{ margin: 0 }}>
                  {s}
                </Tag>
              )
            })}
          </Space>
        )
      },
    },
    {
      title: '评分',
      key: 'score',
      width: 90,
      render: (_: any, r: RunSummary) => {
        if (r.final_score == null) return '-'
        return (
          <Tag color={r.passed ? 'success' : 'error'}>
            {r.final_score} {r.passed ? '通过' : '未过'}
          </Tag>
        )
      },
    },
    {
      title: '归属',
      dataIndex: 'user_id',
      key: 'user_id',
      width: 110,
      ellipsis: true,
      render: (v: string | null) => (
        <Tooltip title={v || ''}>
          <Text style={{ fontSize: 12 }}>
            <UserOutlined /> {v || '匿名'}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (v: string | null) =>
        v ? (
          <Text style={{ fontSize: 12 }}>
            <ClockCircleOutlined /> {dayjs(v).format('YYYY-MM-DD HH:mm')}
          </Text>
        ) : (
          '-'
        ),
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_: any, r: RunSummary) => (
        <Button type="link" onClick={() => openRun(r.run_id)}>
          查看
        </Button>
      ),
    },
  ]

  const stagePanels =
    trace?.traces?.map((t) => {
      const statusColor =
        t.stage_status === 'success'
          ? 'green'
          : t.stage_status === 'failed'
          ? 'red'
          : 'default'
      return {
        key: t.id,
        label: (
          <Space>
            <Tag color="blue">{t.stage}</Tag>
            <span>{t.stage_name || t.stage}</span>
            <Tag color={statusColor}>{t.stage_status}</Tag>
          </Space>
        ),
        children: (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <Text strong>处理方案与原因（每步推理日志）</Text>
              <div style={{ marginTop: 8 }}>
                <ReasoningBlock reasoning={t.reasoning} />
              </div>
            </div>
            <div>
              <Text strong>原始输出</Text>
              <div style={{ marginTop: 8 }}>
                <StageOutput output={t.stage_output} />
              </div>
            </div>
          </div>
        ),
      }
    }) ?? []

  return (
    <div style={{ padding: 24 }}>
      <Tabs
        defaultActiveKey="runs"
        items={[
          {
            key: 'runs',
            label: (
              <span>
                <HistoryOutlined /> 运行记录与每步推理
              </span>
            ),
            children: (
              <Card
                title="个人中心 · 运行记录"
                extra={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    查看你本人 AI 看板生成的每一步「处理方案与原因」；普通用户仅可见自己的运行记录
                  </Text>
                }
              >
                <Spin spinning={loadingRuns}>
                  <Table<RunSummary>
                    rowKey="run_id"
                    columns={runColumns}
                    dataSource={runs}
                    pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
                    size="middle"
                    locale={{ emptyText: <Empty description="暂无运行记录" /> }}
                  />
                </Spin>

                {selectedRunId && (
                  <Card
                    style={{ marginTop: 16 }}
                    size="small"
                    title={`运行详情 · ${selectedRunId.slice(0, 8)}…`}
                    extra={
                      <Space>
                        <Input
                          placeholder="反馈备注（可选）"
                          style={{ width: 200 }}
                          value={note}
                          onChange={(e) => setNote(e.target.value)}
                        />
                        <Button
                          icon={<LikeOutlined />}
                          onClick={() => submitFeedback('like')}
                          loading={submitting}
                        >
                          赞
                        </Button>
                        <Button
                          icon={<DislikeOutlined />}
                          danger
                          onClick={() => submitFeedback('dislike')}
                          loading={submitting}
                        >
                          踩
                        </Button>
                      </Space>
                    }
                  >
                    <Spin spinning={loadingTrace}>
                      {stagePanels.length > 0 ? (
                        <Collapse items={stagePanels} defaultActiveKey={stagePanels.map((p) => p.key)} />
                      ) : (
                        <Empty description="暂无阶段明细" />
                      )}
                    </Spin>
                  </Card>
                )}
              </Card>
            ),
          },
        ]}
      />
    </div>
  )
}
