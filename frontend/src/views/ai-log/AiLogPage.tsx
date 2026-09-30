import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Card,
  Table,
  DatePicker,
  Select,
  Input,
  Button,
  Space,
  Tag,
  Popover,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'
import { http } from '@/utils/request'

const { RangePicker } = DatePicker
const { Text } = Typography

interface AiLogItem {
  id: string
  session_id?: string | null
  dashboard_id?: string | null
  user_id?: string | null
  intent?: string | null
  action_type?: string | null
  params_summary?: any
  result_status?: string | null
  error_msg?: string | null
  llm_layer?: string | null
  latency_ms?: number | null
  created_at?: string | null
}

interface ListResp {
  total: number
  page: number
  page_size: number
  items: AiLogItem[]
}

const ACTION_TYPE_OPTIONS = [
  'add_chart',
  'change_chart',
  'delete_chart',
  'undo',
  'remove',
  'unknown',
  'fallback',
  'action_error',
  'stream_error',
]
const RESULT_OPTIONS = ['success', 'failed']
const LLM_LAYER_OPTIONS = ['rule', 'llm', 'llm_add_chart', 'confirmation_word']

function toOptions(list: string[]) {
  return list.map((o) => ({ label: o, value: o }))
}

export default function AiLogPage() {
  const [data, setData] = useState<AiLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({
    action_type: undefined as string | undefined,
    result_status: undefined as string | undefined,
    llm_layer: undefined as string | undefined,
    session_id: '',
    dashboard_id: '',
    keyword: '',
    range: null as [Dayjs, Dayjs] | null,
  })

  const load = useCallback(
    async (p: number, ps: number) => {
      setLoading(true)
      try {
        const params: Record<string, any> = {
          page: p,
          page_size: ps,
          action_type: filters.action_type,
          result_status: filters.result_status,
          llm_layer: filters.llm_layer,
          session_id: filters.session_id || undefined,
          dashboard_id: filters.dashboard_id || undefined,
          keyword: filters.keyword || undefined,
        }
        if (filters.range && filters.range[0] && filters.range[1]) {
          // 以 UTC ISO 发送，与后端存储(naive UTC)一致，过滤才准确
          params.start_time = filters.range[0].toISOString()
          params.end_time = filters.range[1].toISOString()
        }
        const res = await http.get<ListResp>('/ai-action-log/list', params)
        setData(res?.items ?? [])
        setTotal(res?.total ?? 0)
      } catch (e: any) {
        message.error(e?.message || '加载 AI 操作日志失败')
      } finally {
        setLoading(false)
      }
    },
    [filters],
  )

  // 仅首次挂载拉取一次；后续由「查询 / 分页」显式触发，避免筛选输入时频繁请求
  const mounted = useRef(false)
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true
      load(1, pageSize)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load])

  const resetFilters = () => {
    setFilters({
      action_type: undefined,
      result_status: undefined,
      llm_layer: undefined,
      session_id: '',
      dashboard_id: '',
      keyword: '',
      range: null,
    })
    setPage(1)
    load(1, pageSize)
  }

  const columns: ColumnsType<AiLogItem> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 175,
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '用户',
      dataIndex: 'user_id',
      key: 'user_id',
      width: 120,
      render: (v: string | null) => v || '-',
    },
    {
      title: '看板ID',
      dataIndex: 'dashboard_id',
      key: 'dashboard_id',
      width: 140,
      ellipsis: true,
      render: (v: string | null) =>
        v ? <Text style={{ fontSize: 12 }}>{v}</Text> : '-',
    },
    {
      title: '意图',
      dataIndex: 'intent',
      key: 'intent',
      width: 110,
      render: (v: string | null) => v || '-',
    },
    {
      title: '动作',
      dataIndex: 'action_type',
      key: 'action_type',
      width: 130,
      render: (v: string | null) =>
        v ? <Tag color="blue">{v}</Tag> : '-',
    },
    {
      title: '结果',
      dataIndex: 'result_status',
      key: 'result_status',
      width: 90,
      render: (v: string | null) =>
        v ? (
          <Tag color={v === 'success' ? 'success' : 'error'}>{v}</Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '模型层',
      dataIndex: 'llm_layer',
      key: 'llm_layer',
      width: 140,
      render: (v: string | null) => v || '-',
    },
    {
      title: '耗时',
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 90,
      render: (v: number | null) => (v != null ? `${v}ms` : '-'),
    },
    {
      title: '参数摘要',
      dataIndex: 'params_summary',
      key: 'params_summary',
      width: 160,
      render: (v: any) => {
        if (!v) return '-'
        const s = JSON.stringify(v)
        const short = s.length > 40 ? s.slice(0, 40) + '…' : s
        return (
          <Popover
            title="参数摘要"
            content={
              <pre
                style={{
                  maxWidth: 380,
                  maxHeight: 240,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  margin: 0,
                }}
              >
                {s}
              </pre>
            }
          >
            <span style={{ cursor: 'pointer' }}>{short}</span>
          </Popover>
        )
      },
    },
    {
      title: '错误信息',
      dataIndex: 'error_msg',
      key: 'error_msg',
      width: 220,
      render: (v: string | null) => {
        if (!v) return '-'
        const short = v.length > 30 ? v.slice(0, 30) + '…' : v
        return (
          <Popover
            title="错误详情"
            content={
              <div
                style={{
                  maxWidth: 380,
                  maxHeight: 240,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  color: '#ff4d4f',
                }}
              >
                {v}
              </div>
            }
          >
            <span style={{ color: '#ff4d4f', cursor: 'pointer' }}>{short}</span>
          </Popover>
        )
      },
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card
        title="AI 操作日志"
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            记录每次 AI 对话动作的意图 / 动作 / 结果 / 耗时（仅可见自己或授权范围的数据）
          </Text>
        }
      >
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            allowClear
            placeholder="动作类型"
            style={{ width: 150 }}
            value={filters.action_type}
            onChange={(v) => setFilters((f) => ({ ...f, action_type: v }))}
            options={toOptions(ACTION_TYPE_OPTIONS)}
          />
          <Select
            allowClear
            placeholder="结果"
            style={{ width: 120 }}
            value={filters.result_status}
            onChange={(v) => setFilters((f) => ({ ...f, result_status: v }))}
            options={toOptions(RESULT_OPTIONS)}
          />
          <Select
            allowClear
            placeholder="模型层"
            style={{ width: 160 }}
            value={filters.llm_layer}
            onChange={(v) => setFilters((f) => ({ ...f, llm_layer: v }))}
            options={toOptions(LLM_LAYER_OPTIONS)}
          />
          <Input
            allowClear
            placeholder="会话ID"
            style={{ width: 160 }}
            value={filters.session_id}
            onChange={(e) =>
              setFilters((f) => ({ ...f, session_id: e.target.value }))
            }
          />
          <Input
            allowClear
            placeholder="看板ID"
            style={{ width: 160 }}
            value={filters.dashboard_id}
            onChange={(e) =>
              setFilters((f) => ({ ...f, dashboard_id: e.target.value }))
            }
          />
          <Input
            allowClear
            placeholder="关键词(错误/动作)"
            style={{ width: 200 }}
            value={filters.keyword}
            onChange={(e) =>
              setFilters((f) => ({ ...f, keyword: e.target.value }))
            }
          />
          <RangePicker
            value={filters.range}
            onChange={(v) =>
              setFilters((f) => ({
                ...f,
                range: (v as [Dayjs, Dayjs] | null) ?? null,
              }))
            }
          />
          <Button
            type="primary"
            onClick={() => {
              setPage(1)
              load(1, pageSize)
            }}
          >
            查询
          </Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>

        <Table<AiLogItem>
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 1100 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={(pagination) => {
            const p = pagination.current || 1
            const ps = pagination.pageSize || 20
            setPage(p)
            setPageSize(ps)
            load(p, ps)
          }}
        />
      </Card>
    </div>
  )
}
