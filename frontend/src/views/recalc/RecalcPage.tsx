import React, { useEffect, useState } from 'react'
import { Card, Button, Select, Table, Tag, Tabs, message, Space, Input, Empty, Typography } from 'antd'
import { http } from '../../utils/request'

const { Text, Paragraph } = Typography

type Scope = 'financial' | 'risk' | 'business' | 'other'

interface HistoryRow {
  recalc_id: string
  status: string
  scope: string | null
  affected_count: number
  trigger_action?: string
  created_at?: number
}

export default function RecaclPage() {
  const [scope, setScope] = useState<Scope>('risk')
  const [status, setStatus] = useState<any>(null)
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [graph, setGraph] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const loadStatus = () => {
    http.get('/api/v1/recalc/status').then((r: any) => setStatus(r)).catch(() => message.error('状态加载失败'))
  }
  const loadHistory = () => {
    http.get('/api/v1/recalc/history').then((r: any) => setHistory((r?.history || []).map((h: any) => ({
      recalc_id: h.recalc_id, status: h.status, scope: h.scope,
      affected_count: h.affected_count, trigger_action: h.trigger_action, created_at: h.created_at,
    })))).catch(() => message.error('历史加载失败'))
  }
  const loadGraph = () => {
    http.get('/api/v1/recalc/dependency-graph').then((r: any) => setGraph(r)).catch(() => message.error('依赖图加载失败'))
  }

  useEffect(() => { loadStatus(); loadHistory(); loadGraph() }, [])

  const trigger = () => {
    setLoading(true)
    http.post('/api/v1/recalc/trigger', { scope, dry_run: false })
      .then((r: any) => {
        message.success('已触发下游重算')
        loadStatus(); loadHistory()
        setStatus(r)
      })
      .catch((e: any) => message.error('触发失败：' + (e?.message || e)))
      .finally(() => setLoading(false))
  }

  const statusColor = (s: string) => {
    if (s === 'done') return 'green'
    if (s === 'done_with_warnings') return 'gold'
    if (s === 'failed') return 'red'
    if (s === 'running') return 'blue'
    if (s === 'recovered') return 'purple'
    return 'default'
  }

  const graphTab = () => {
    if (!graph) return <Empty description="无依赖图" />
    const byCat: Record<string, any[]> = {}
    ;(graph.nodes || []).forEach((n: any) => {
      if (n.category === 'source') return
      byCat[n.category] = byCat[n.category] || []
      byCat[n.category].push(n)
    })
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        {Object.keys(byCat).map((cat) => (
          <Card key={cat} size="small" title={`分类：${cat}`}>
            <Space wrap>
              {byCat[cat].map((n: any) => (
                <Tag key={n.id} color="blue">{n.name}</Tag>
              ))}
            </Space>
          </Card>
        ))}
        <Paragraph type="secondary">依赖边（源→指标）共 {(graph.edges || []).length} 条；修改某层数据后，对应分类下的指标会自动进入重算队列。</Paragraph>
      </Space>
    )
  }

  const historyColumns = [
    { title: '重算ID', dataIndex: 'recalc_id', key: 'recalc_id', ellipsis: true },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={statusColor(s)}>{s}</Tag> },
    { title: '范围', dataIndex: 'scope', key: 'scope', render: (v: any) => v || '-' },
    { title: '影响指标数', dataIndex: 'affected_count', key: 'affected_count' },
    { title: '触发动作', dataIndex: 'trigger_action', key: 'trigger_action', render: (v: any) => v || '-' },
  ]

  return (
    <div style={{ padding: 24 }}>
      <h2>下游重算一致性（C-16）</h2>
      <Paragraph type="secondary">
        数据修改（配置/规则/批量数据）后，下游派生指标自动重算，保证链路一致性。可手动触发 / 查看状态 / 查看历史 / 查看依赖图。
      </Paragraph>

      <Tabs defaultActiveKey="status">
        <Tabs.TabPane tab="重算状态" key="status">
          <Card size="small">
            <Space wrap>
              <Select<Scope> value={scope} style={{ width: 180 }} onChange={setScope}
                options={[
                  { value: 'financial', label: '财务' },
                  { value: 'risk', label: '风控' },
                  { value: 'business', label: '业务' },
                  { value: 'other', label: '其他' },
                ]} />
              <Button type="primary" loading={loading} onClick={trigger}>触发下游重算</Button>
              <Button onClick={() => { loadStatus(); loadHistory() }}>刷新</Button>
            </Space>
            {status && (
              <div style={{ marginTop: 16 }}>
                <Text strong>队列：</Text>
                <Space wrap style={{ marginLeft: 8 }}>
                  <Tag color={status.queue?.pending ? 'blue' : 'default'}>待执行 {status.queue?.pending ?? 0}</Tag>
                  <Tag color={status.queue?.running ? 'blue' : 'default'}>执行中 {status.queue?.running ?? 0}</Tag>
                  <Tag color={status.queue?.done ? 'green' : 'default'}>完成 {status.queue?.done ?? 0}</Tag>
                  <Tag color={status.queue?.failed ? 'red' : 'default'}>失败 {status.queue?.failed ?? 0}</Tag>
                </Space>
                {status.latest && (
                  <Paragraph style={{ marginTop: 8 }}>
                    最近一次：<Tag color={statusColor(status.latest.status)}>{status.latest.status}</Tag>
                    影响 {status.latest.affected_count} 个指标
                  </Paragraph>
                )}
              </div>
            )}
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="重算历史" key="history">
          <Card size="small">
            <Table<HistoryRow> rowKey="recalc_id" size="small" dataSource={history} columns={historyColumns}
              pagination={{ pageSize: 8 }} locale={{ emptyText: <Empty description="暂无重算记录" /> }} />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="依赖关系图" key="graph">
          <Card size="small">{graphTab()}</Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  )
}
