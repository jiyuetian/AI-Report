import React, { useEffect, useState } from 'react'
import { Card, Button, Select, Table, Tag, Tabs, message, Space, Empty, Typography, Statistic, Row, Col } from 'antd'
import { http } from '../../utils/request'

const { Text, Paragraph } = Typography

type Range = 'all' | '1h' | '24h' | '7d' | '30d'

export default function UsageStatsPage() {
  const [range, setRange] = useState<Range>('all')
  const [overview, setOverview] = useState<any>(null)
  const [patterns, setPatterns] = useState<any>(null)
  const [events, setEvents] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const loadOverview = (rg: Range) => {
    setLoading(true)
    http.get('/api/v1/usage-stats/overview', { params: { time_range: rg } })
      .then((r: any) => setOverview(r))
      .catch(() => message.error('统计概览加载失败'))
      .finally(() => setLoading(false))
  }
  const loadPatterns = () => {
    http.get('/api/v1/usage-stats/patterns')
      .then((r: any) => setPatterns(r))
      .catch(() => message.error('使用模式加载失败'))
  }
  const loadEvents = () => {
    http.get('/api/v1/usage-stats/events', { params: { limit: 50 } })
      .then((r: any) => setEvents(Array.isArray(r) ? r : []))
      .catch(() => message.error('事件流加载失败'))
  }

  useEffect(() => { loadOverview(range); loadPatterns(); loadEvents() }, [])

  const onRange = (rg: Range) => { setRange(rg); loadOverview(rg) }

  const modelColumns = [
    { title: '模型', dataIndex: 'model', key: 'model' },
    { title: '调用次数', dataIndex: 'calls', key: 'calls' },
    {
      title: '成功率', dataIndex: 'success_rate', key: 'success_rate',
      render: (v: number) => <Tag color={v >= 0.99 ? 'green' : v >= 0.9 ? 'gold' : 'red'}>{((v || 0) * 100).toFixed(1)}%</Tag>,
    },
    { title: 'Prompt Tokens', dataIndex: 'prompt_tokens', key: 'prompt_tokens' },
    { title: 'Completion Tokens', dataIndex: 'completion_tokens', key: 'completion_tokens' },
    { title: '总 Tokens', dataIndex: 'total_tokens', key: 'total_tokens' },
    { title: '平均延迟(ms)', dataIndex: 'avg_latency_ms', key: 'avg_latency_ms' },
  ]
  const actionColumns = [
    { title: '动作类型', dataIndex: 'action_type', key: 'action_type' },
    { title: '次数', dataIndex: 'count', key: 'count' },
    {
      title: '成功率', dataIndex: 'success_rate', key: 'success_rate',
      render: (v: number) => <Tag color={v >= 0.99 ? 'green' : v >= 0.9 ? 'gold' : 'red'}>{((v || 0) * 100).toFixed(1)}%</Tag>,
    },
    { title: '平均延迟(ms)', dataIndex: 'avg_latency_ms', key: 'avg_latency_ms' },
  ]
  const eventColumns = [
    { title: '时间(UTC)', dataIndex: 'ts', key: 'ts', ellipsis: true },
    { title: '事件', dataIndex: 'event_type', key: 'event_type', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '用户(脱敏)', dataIndex: 'user', key: 'user' },
    {
      title: '结果', dataIndex: 'success', key: 'success',
      render: (v: any) => v === undefined ? '-' : <Tag color={v ? 'green' : 'red'}>{v ? '成功' : '失败'}</Tag>,
    },
    { title: '延迟(ms)', dataIndex: 'latency_ms', key: 'latency_ms', render: (v: any) => v ?? '-' },
  ]
  const trendColumns = [
    { title: '时间桶(UTC)', dataIndex: 'ts', key: 'ts', ellipsis: true },
    { title: '总量', dataIndex: 'total', key: 'total' },
    { title: '成功', dataIndex: 'success', key: 'success' },
    { title: '失败', dataIndex: 'error', key: 'error' },
  ]

  const overviewPane = () => {
    if (!overview) return <Empty description="暂无统计数据" />
    const o = overview.overview || {}
    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Row gutter={16}>
          <Col span={6}><Card size="small"><Statistic title="事件总量" value={o.total_events || 0} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="成功率" value={((o.success_rate || 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="总 Token 消耗" value={o.total_tokens || 0} /></Card></Col>
          <Col span={6}><Card size="small"><Statistic title="平均延迟(ms)" value={o.avg_latency_ms || 0} /></Card></Col>
        </Row>
        <Card size="small" title="按动作类型">
          <Table<any> rowKey="action_type" size="small" dataSource={overview.by_action || []} columns={actionColumns}
            pagination={false} locale={{ emptyText: <Empty description="暂无动作统计" /> }} />
        </Card>
        <Card size="small" title="事件类型分布">
          <Space wrap>
            {Object.keys(o.event_types || {}).map((k) => (
              <Tag key={k} color="geekblue">{k}: {o.event_types[k]}</Tag>
            ))}
            {Object.keys(o.event_types || {}).length === 0 && <Text type="secondary">无</Text>}
          </Space>
        </Card>
      </Space>
    )
  }

  const modelPane = () => (
    <Card size="small">
      <Table<any> rowKey="model" size="small" dataSource={overview?.by_model || []} columns={modelColumns}
        pagination={false} locale={{ emptyText: <Empty description="暂无模型调用统计" /> }} />
      <Paragraph type="secondary" style={{ marginTop: 8 }}>
        模型使用量 / 成功率 / token 消耗来自 LLM 网关真实调用埋点（用户标识已脱敏，数据仅存进程内存、不落库）。
      </Paragraph>
    </Card>
  )

  const trendPane = () => (
    <Card size="small">
      <Table<any> rowKey="bucket" size="small" dataSource={overview?.trends || []} columns={trendColumns}
        pagination={{ pageSize: 12 }} locale={{ emptyText: <Empty description="暂无趋势数据" /> }} />
    </Card>
  )

  const patternPane = () => {
    if (!patterns) return <Empty description="暂无模式分析" />
    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Card size="small" title="最常用动作 Top">
          <Space wrap>
            {(patterns.top_actions || []).map((a: any) => (
              <Tag key={a.action_type} color="blue">{a.action_type}: {a.count}</Tag>
            ))}
            {(patterns.top_actions || []).length === 0 && <Text type="secondary">无</Text>}
          </Space>
        </Card>
        <Card size="small" title="模型偏好占比">
          <Space wrap>
            {Object.keys(patterns.model_preference || {}).map((m) => (
              <Tag key={m} color="purple">{m}: {((patterns.model_preference[m] || 0) * 100).toFixed(1)}%</Tag>
            ))}
            {Object.keys(patterns.model_preference || {}).length === 0 && <Text type="secondary">无</Text>}
          </Space>
        </Card>
        <Card size="small" title="各模型错误率">
          <Space wrap>
            {Object.keys(patterns.error_rate_by_model || {}).map((m) => (
              <Tag key={m} color={(patterns.error_rate_by_model[m] || 0) > 0 ? 'red' : 'green'}>
                {m}: {((patterns.error_rate_by_model[m] || 0) * 100).toFixed(1)}%
              </Tag>
            ))}
            {Object.keys(patterns.error_rate_by_model || {}).length === 0 && <Text type="secondary">无</Text>}
          </Space>
        </Card>
        <Card size="small" title="高峰时段 / 最慢模型 / 7日对比">
          <Paragraph>
            高峰时段(UTC)：<Text strong>{patterns.peak_hour_utc >= 0 ? patterns.peak_hour_utc + ':00' : '无数据'}</Text>
          </Paragraph>
          <Space wrap>
            {(patterns.slowest_models || []).map((m: any) => (
              <Tag key={m.model} color="volcano">{m.model}: {m.avg_latency_ms}ms</Tag>
            ))}
            {(patterns.slowest_models || []).length === 0 && <Text type="secondary">无</Text>}
          </Space>
          {patterns.compare_7d && (
            <Paragraph style={{ marginTop: 8 }}>
              7日对比：前段成功率 {(patterns.compare_7d.before?.success_rate * 100).toFixed(1)}% →
              后段 {(patterns.compare_7d.after?.success_rate * 100).toFixed(1)}%
              （Δ {(patterns.compare_7d.delta_success_rate * 100).toFixed(1)}%，{patterns.compare_7d.trend}）
            </Paragraph>
          )}
        </Card>
        <Card size="small" title="最近事件流">
          <Table<any> rowKey="ts" size="small" dataSource={events} columns={eventColumns}
            pagination={{ pageSize: 10 }} locale={{ emptyText: <Empty description="暂无事件" /> }} />
        </Card>
      </Space>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <h2>AI 使用统计（J-8）</h2>
      <Paragraph type="secondary">
        统计 AI 动作与模型调用的使用情况：模型使用量 / 成功率 / token 消耗可见，支持按时间范围筛选与模式分析。
        数据内存态、用户脱敏、零 DB（生产库不受影响）。
      </Paragraph>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select<Range> value={range} style={{ width: 160 }} onChange={onRange}
          options={[
            { value: 'all', label: '全部' },
            { value: '1h', label: '近 1 小时' },
            { value: '24h', label: '近 24 小时' },
            { value: '7d', label: '近 7 天' },
            { value: '30d', label: '近 30 天' },
          ]} />
        <Button onClick={() => { loadOverview(range); loadPatterns(); loadEvents() }}>刷新</Button>
      </Space>
      <Tabs defaultActiveKey="overview">
        <Tabs.TabPane tab="概览" key="overview">{overviewPane()}</Tabs.TabPane>
        <Tabs.TabPane tab="按模型" key="model">{modelPane()}</Tabs.TabPane>
        <Tabs.TabPane tab="趋势" key="trends">{trendPane()}</Tabs.TabPane>
        <Tabs.TabPane tab="使用模式" key="patterns">{patternPane()}</Tabs.TabPane>
      </Tabs>
    </div>
  )
}
