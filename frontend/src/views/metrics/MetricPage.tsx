import React, { useEffect, useState } from 'react'
import {
  Card, Row, Col, InputNumber, Button, Tabs, Tag, Descriptions, Table, Input,
  message, Spin, Empty, Divider, Statistic,
} from 'antd'
import { http } from '../../utils/request'

interface MetricField { field: string; aliases: string[] }
interface MetricMeta {
  key: string
  name: string
  category: string
  formula: string
  formula_expr: string
  unit: string
  aggregation: string
  data_source: string
  description: string
  fields: MetricField[]
}
type PeriodRow = { period: string; values: Record<string, number | undefined> }

const CAT_LABEL: Record<string, string> = {
  financial: '财务',
  risk: '风控',
  business: '业务',
  other: '其他',
}

export default function MetricPage() {
  const [metrics, setMetrics] = useState<MetricMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<MetricMeta | null>(null)
  const [fieldValues, setFieldValues] = useState<Record<string, number | undefined>>({})
  const [periods, setPeriods] = useState<PeriodRow[]>([])
  const [horizon, setHorizon] = useState(3)
  const [result, setResult] = useState<any>(null)
  const [calcLoading, setCalcLoading] = useState(false)

  useEffect(() => {
    http.get<{ success: boolean; count: number; metrics: MetricMeta[] }>('/metrics/registry')
      .then((r) => {
        const list = r.metrics || []
        setMetrics(list)
        if (list.length) selectMetric(list[0])
      })
      .catch((e) => message.error('加载指标注册表失败：' + (e?.message || e)))
      .finally(() => setLoading(false))
  }, [])

  function selectMetric(m: MetricMeta) {
    setSelected(m)
    setResult(null)
    const fv: Record<string, number | undefined> = {}
    m.fields.forEach((f) => { fv[f.field] = undefined })
    setFieldValues(fv)
    setPeriods([
      { period: 'P1', values: { ...fv } },
      { period: 'P2', values: { ...fv } },
    ])
  }

  async function doCalc(operation: string, data: any) {
    if (!selected) return
    setCalcLoading(true)
    setResult(null)
    try {
      const r = await http.post<any>('/metrics/calculate', { metric: selected.key, operation, data })
      setResult(r)
      if (!r.success) message.error(r.error || '计算失败')
    } catch (e: any) {
      message.error('计算请求失败：' + (e?.message || e))
    } finally {
      setCalcLoading(false)
    }
  }

  function updatePeriod(i: number, field: string, val: number | null) {
    setPeriods((prev) => {
      const next = prev.slice()
      next[i] = { ...next[i], values: { ...next[i].values, [field]: val ?? undefined } }
      return next
    })
  }

  function renderQuery() {
    if (!selected) return null
    return (
      <div>
        <Descriptions column={1} size="small" bordered style={{ marginBottom: 16 }}>
          <Descriptions.Item label="公式">{selected.formula}</Descriptions.Item>
          <Descriptions.Item label="表达式">{selected.formula_expr}</Descriptions.Item>
          <Descriptions.Item label="数据来源">{selected.data_source}</Descriptions.Item>
          <Descriptions.Item label="含义">{selected.description}</Descriptions.Item>
        </Descriptions>
        <Row gutter={12}>
          {selected.fields.map((f) => (
            <Col span={8} key={f.field} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>
                {f.field}
                {f.aliases.length ? '（' + f.aliases.join(' / ') + '）' : ''}
              </div>
              <InputNumber
                style={{ width: '100%' }}
                placeholder="输入数值"
                value={fieldValues[f.field]}
                onChange={(v) => setFieldValues((p) => ({ ...p, [f.field]: v ?? undefined }))}
              />
            </Col>
          ))}
        </Row>
        <Button type="primary" loading={calcLoading} onClick={() => doCalc('query', fieldValues)}>
          计算 {selected.name}
        </Button>
        {result && result.success && (
          <Statistic
            title={`${selected.name}（${result.operation}）`}
            value={result.value}
            suffix={result.unit}
            style={{ marginTop: 16 }}
          />
        )}
      </div>
    )
  }

  function renderPeriodTable() {
    if (!selected) return null
    const cols = [
      {
        title: '期次',
        dataIndex: 'period',
        width: 120,
        render: (_: any, _row: PeriodRow, i: number) => (
          <Input
            value={periods[i]?.period}
            onChange={(e) =>
              setPeriods((prev) => {
                const next = prev.slice()
                next[i] = { ...next[i], period: e.target.value }
                return next
              })
            }
          />
        ),
      },
      ...selected.fields.map((f) => ({
        title: f.field,
        dataIndex: f.field,
        render: (_: any, _row: PeriodRow, i: number) => (
          <InputNumber
            style={{ width: '100%' }}
            value={periods[i]?.values[f.field]}
            onChange={(v) => updatePeriod(i, f.field, v)}
          />
        ),
      })),
      {
        title: '操作',
        width: 80,
        render: (_: any, _row: PeriodRow, i: number) => (
          <Button
            danger
            size="small"
            disabled={periods.length <= 2}
            onClick={() => setPeriods((prev) => prev.filter((_, idx) => idx !== i))}
          >
            删
          </Button>
        ),
      },
    ]
    return (
      <div>
        <Table
          rowKey={(_, i) => String(i)}
          dataSource={periods}
          columns={cols as any}
          pagination={false}
          size="small"
        />
        <Button
          style={{ marginTop: 8 }}
          onClick={() => setPeriods((prev) => [...prev, { period: `P${prev.length + 1}`, values: { ...fieldValues } }])}
        >
          + 增加一期
        </Button>
      </div>
    )
  }

  function renderCompare() {
    return (
      <div>
        {renderPeriodTable()}
        <Button type="primary" style={{ marginTop: 12 }} loading={calcLoading} onClick={() => doCalc('compare', { periods })}>
          多期对比
        </Button>
        {result && result.success && result.operation === 'compare' && (
          <div style={{ marginTop: 16 }}>
            <Table
              rowKey={(_, i) => String(i)}
              dataSource={(result.series || []).map((s: any, i: number) => ({ ...s, idx: i }))}
              columns={[
                { title: '期次', dataIndex: 'period' },
                { title: '数值', dataIndex: 'value', render: (v: any) => (v == null ? '—' : `${v}${result.unit}`) },
                { title: '状态', dataIndex: 'success', render: (ok: boolean) => (ok ? '成功' : '失败') },
                { title: '说明', dataIndex: 'error' },
              ]}
              pagination={false}
              size="small"
            />
            <div style={{ marginTop: 8 }}>首尾变化：<b>{result.delta_pct}%</b></div>
          </div>
        )}
      </div>
    )
  }

  function renderTrend() {
    return (
      <div>
        {renderPeriodTable()}
        <div style={{ marginTop: 12 }}>
          <span style={{ marginRight: 8 }}>预测期数</span>
          <InputNumber min={1} max={12} value={horizon} onChange={(v) => setHorizon(v ?? 3)} />
        </div>
        <Button type="primary" style={{ marginTop: 12 }} loading={calcLoading} onClick={() => doCalc('trend', { history: periods, horizon })}>
          趋势预测
        </Button>
        {result && result.success && result.operation === 'trend' && (
          <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 8 }}>方法：{result.method}，斜率 {result.slope}</div>
            <Sparkline history={result.history || []} forecast={result.forecast || []} />
            <Table
              rowKey={(_, i) => String(i)}
              dataSource={[
                ...(result.history || []).map((h: any) => ({ ...h, kind: '历史' })),
                ...(result.forecast || []).map((h: any) => ({ ...h, kind: '预测' })),
              ]}
              columns={[
                { title: '类型', dataIndex: 'kind' },
                { title: '期次', dataIndex: 'period' },
                { title: '数值', dataIndex: 'value', render: (v: any) => `${v}${result.unit}` },
              ]}
              pagination={false}
              size="small"
            />
          </div>
        )}
      </div>
    )
  }

  function renderExplain() {
    return (
      <div>
        <Button type="primary" loading={calcLoading} onClick={() => doCalc('explain', {})}>
          解释 {selected?.name}
        </Button>
        {result && result.success && result.operation === 'explain' && (
          <Descriptions column={1} size="small" bordered style={{ marginTop: 16 }}>
            <Descriptions.Item label="公式">{result.formula}</Descriptions.Item>
            <Descriptions.Item label="表达式">{result.formula_expr}</Descriptions.Item>
            <Descriptions.Item label="数据来源">{result.data_source}</Descriptions.Item>
            <Descriptions.Item label="聚合方式">{result.aggregation}</Descriptions.Item>
            <Descriptions.Item label="字段">
              {(result.fields || []).map((f: any) => (
                <Tag key={f.field}>
                  {f.field}：{(f.aliases || []).join(' / ')}
                </Tag>
              ))}
            </Descriptions.Item>
            <Descriptions.Item label="含义">{result.description}</Descriptions.Item>
          </Descriptions>
        )}
      </div>
    )
  }

  if (loading) return <div style={{ padding: 48, textAlign: 'center' }}><Spin /></div>

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginTop: 0 }}>派生指标（{metrics.length} 个）</h2>
      <Row gutter={[12, 12]}>
        {metrics.map((m) => (
          <Col xs={12} sm={8} md={6} lg={6} xl={4} key={m.key}>
            <Card
              hoverable
              onClick={() => selectMetric(m)}
              style={{
                borderColor: selected?.key === m.key ? '#1677ff' : undefined,
                height: '100%',
              }}
              title={m.name}
              extra={<Tag color="blue">{CAT_LABEL[m.category] || m.category}</Tag>}
            >
              <div style={{ fontSize: 12, color: '#666', minHeight: 36 }}>{m.formula}</div>
              <Tag>{m.unit}</Tag>
            </Card>
          </Col>
        ))}
      </Row>
      <Divider />
      {selected ? (
        <Tabs
          items={[
            { key: 'query', label: '指标计算', children: renderQuery() },
            { key: 'compare', label: '多期对比', children: renderCompare() },
            { key: 'trend', label: '趋势预测', children: renderTrend() },
            { key: 'explain', label: '指标解释', children: renderExplain() },
          ]}
        />
      ) : (
        <Empty description="请选择左侧指标" />
      )}
    </div>
  )
}

function Sparkline({ history, forecast }: { history: any[]; forecast: any[] }) {
  const all = [...history, ...forecast].map((p) => Number(p.value))
  if (all.length < 2) return null
  const w = 600
  const h = 120
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1
  const pts = all
    .map((v, i) => {
      const x = (i / (all.length - 1)) * (w - 20) + 10
      const y = h - 10 - ((v - min) / span) * (h - 20)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const splitX = ((history.length - 1) / (all.length - 1)) * (w - 20) + 10
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ background: '#fafafa', border: '1px solid #eee', marginBottom: 8 }}>
      <line x1={splitX} y1={0} x2={splitX} y2={h} stroke="#bbb" strokeDasharray="4 4" />
      <polyline points={pts} fill="none" stroke="#1677ff" strokeWidth={2} />
    </svg>
  )
}
