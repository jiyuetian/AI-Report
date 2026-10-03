import React, { useState } from 'react'
import { Card, Button, Table, Tag, message, Space, Empty, Typography, Statistic, Row, Col, Alert } from 'antd'
import { http } from '../utils/request'

const { Text, Paragraph } = Typography

export default function E2ETestPage() {
  const [report, setReport] = useState<any>(null)
  const [running, setRunning] = useState(false)

  const runAll = () => {
    setRunning(true)
    http.post('/api/v1/integration/run')
      .then((r: any) => { setReport(r); message.success('联调完成') })
      .catch((e: any) => message.error('联调失败：' + (e?.message || e)))
      .finally(() => setRunning(false))
  }
  const loadReport = () => {
    http.get('/api/v1/integration/report')
      .then((r: any) => setReport(r))
      .catch(() => message.error('报告加载失败'))
  }

  const resultColumns = [
    { title: '用例', dataIndex: 'id', key: 'id' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '分组', dataIndex: 'group', key: 'group', render: (v: string) => <Tag color="default">{v}</Tag> },
    {
      title: '结果', dataIndex: 'passed', key: 'passed',
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? 'PASS' : 'FAIL'}</Tag>,
    },
    { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true },
    { title: '耗时(ms)', dataIndex: 'latency_ms', key: 'latency_ms' },
  ]

  const perf = report?.performance
  return (
    <div style={{ padding: 24 }}>
      <h2>全链路联调（Task K）</h2>
      <Paragraph type="secondary">
        离线集成测试运行器：驱动 Task G/H/I/J 各内存态引擎做协同 smoke 集成，验证多模块可装配、调用不崩、返回形态符合契约。
        零 DB、零 LLM 网络调用；真实端到端（浏览器 UI + 生产库）由本机手动验收。
      </Paragraph>
      <Space wrap style={{ marginBottom: 16 }}>
        <Button type="primary" loading={running} onClick={runAll}>运行全链路联调</Button>
        <Button onClick={loadReport}>查看最近报告</Button>
      </Space>

      {!report && <Empty description="尚未运行，点击「运行全链路联调」" />}

      {report && (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert
            type={report.failed === 0 ? 'success' : 'error'}
            message={`通过率 ${((report.pass_rate || 0) * 100).toFixed(0)}%（${report.passed}/${report.total}）· 模式：${report.mode || 'offline'}`}
          />
          <Row gutter={16}>
            <Col span={6}><Card size="small"><Statistic title="用例总数" value={report.total || 0} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="通过" value={report.passed || 0} valueStyle={{ color: '#3f8600' }} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="失败" value={report.failed || 0} valueStyle={{ color: '#cf1322' }} /></Card></Col>
            <Col span={6}><Card size="small"><Statistic title="通过率" value={((report.pass_rate || 0) * 100).toFixed(0)} suffix="%" /></Card></Col>
          </Row>

          {perf && (
            <Card size="small" title={`性能基准（迭代 ${perf.iterations} 次，毫秒）`}>
              <Row gutter={16}>
                <Col span={12}>
                  <Paragraph strong>派生指标 calculate</Paragraph>
                  <Text>p50 {perf.metric_calc_ms?.p50} / p95 {perf.metric_calc_ms?.p95} / max {perf.metric_calc_ms?.max} / mean {perf.metric_calc_ms?.mean}</Text>
                </Col>
                <Col span={12}>
                  <Paragraph strong>使用统计 往返</Paragraph>
                  <Text>p50 {perf.usage_roundtrip_ms?.p50} / p95 {perf.usage_roundtrip_ms?.p95} / max {perf.usage_roundtrip_ms?.max} / mean {perf.usage_roundtrip_ms?.mean}</Text>
                </Col>
              </Row>
            </Card>
          )}

          <Card size="small" title="逐条结果">
            <Table<any> rowKey="id" size="small" dataSource={report.results || []} columns={resultColumns}
              pagination={false} />
          </Card>
        </Space>
      )}
    </div>
  )
}
