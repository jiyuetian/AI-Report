import { useState, useEffect } from 'react'
import { Card, Table, Progress, Tag, Button, Select, Alert, Space, Typography, List } from 'antd'
import { CheckCircleOutlined, WarningOutlined, CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import './QualityPage.css'

const { Title, Text } = Typography
const { Option } = Select

interface QualityIssue {
  type: string
  severity: 'blocking' | 'warning'
  column: string
  row_count: number
  message: string
  sample_values: any[]
  rule: string
}

interface ProfileField {
  column: string
  inferred_type: string
  null_rate: number
  cardinality: number
  duckdb_type: string
}

interface GrainInfo {
  grain_type: string
  grain_desc: string
  total_rows: number
}

interface QualityData {
  dataset_id: string
  table_name: string
  total_rows: number
  column_count: number
  profiles: ProfileField[]
  grain: GrainInfo
  issues: QualityIssue[]
  summary: {
    total_issues: number
    blocking_count: number
    warning_count: number
    by_type: Record<string, number>
    can_proceed: boolean
  }
}

interface QualityPageProps {
  datasetId: string
}

export default function QualityPage({ datasetId }: QualityPageProps) {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<QualityData | null>(null)
  const [editedTypes, setEditedTypes] = useState<Record<string, string>>({})

  // 模拟加载质检数据
  useEffect(() => {
    loadQualityData()
  }, [datasetId])

  const loadQualityData = async () => {
    setLoading(true)
    // TODO: 调用API
    // const response = await fetch(`/api/v1/datasets/${datasetId}/profile`)
    // const result = await response.json()
    
    // 模拟数据
    const mockData: QualityData = {
      dataset_id: datasetId,
      table_name: `ds_${datasetId}`,
      total_rows: 1000,
      column_count: 6,
      profiles: [
        { column: '借据编号', inferred_type: 'id', null_rate: 0.05, cardinality: 950, duckdb_type: 'VARCHAR' },
        { column: '放款日期', inferred_type: 'datetime', null_rate: 0, cardinality: 365, duckdb_type: 'VARCHAR' },
        { column: '到期日期', inferred_type: 'datetime', null_rate: 0, cardinality: 365, duckdb_type: 'VARCHAR' },
        { column: '贷款金额', inferred_type: 'integer', null_rate: 0, cardinality: 500, duckdb_type: 'BIGINT' },
        { column: '担保类型', inferred_type: 'categorical', null_rate: 0, cardinality: 3, duckdb_type: 'VARCHAR' },
        { column: '抵押率', inferred_type: 'float', null_rate: 0.02, cardinality: 50, duckdb_type: 'DOUBLE' }
      ],
      grain: {
        grain_type: 'single_record',
        grain_desc: '单笔借据',
        total_rows: 1000
      },
      issues: [
        { type: 'null', severity: 'blocking', column: '借据编号', row_count: 50, message: '空值率 5.0% 超过阈值 1.0%', sample_values: ['NULL', 'NULL'], rule: '空值检测' },
        { type: 'format', severity: 'blocking', column: '放款日期', row_count: 30, message: '检测到 3 种日期格式', sample_values: ['2024-01-01', '2024/01/01'], rule: '日期格式检测' },
        { type: 'unique', severity: 'warning', column: '借据编号', row_count: 20, message: '检测到 10 个重复值', sample_values: ['JJ001', 'JJ002'], rule: '唯一性检测' },
        { type: 'range', severity: 'warning', column: '抵押率', row_count: 5, message: '抵押率超出 0-100% 范围', sample_values: ['1.2', '1.5'], rule: '抵押率范围检测' },
        { type: 'logic', severity: 'warning', column: '放款日期, 到期日期', row_count: 3, message: '到期日期早于放款日期', sample_values: ['2024-01-01 -> 2024-01-05'], rule: '日期逻辑检测' },
        { type: 'code', severity: 'warning', column: '担保类型', row_count: 10, message: "使用'其它'码值", sample_values: ['其它', '其它'], rule: '码值规范性检测' }
      ],
      summary: {
        total_issues: 6,
        blocking_count: 2,
        warning_count: 4,
        by_type: { null: 1, format: 1, unique: 1, range: 1, logic: 1, code: 1 },
        can_proceed: false
      }
    }
    
    setData(mockData)
    setLoading(false)
  }

  // 计算质量分
  const calculateScore = () => {
    if (!data) return 0
    const baseScore = 100
    const blockingPenalty = data.summary.blocking_count * 20
    const warningPenalty = data.summary.warning_count * 5
    return Math.max(0, baseScore - blockingPenalty - warningPenalty)
  }

  const score = calculateScore()
  const scoreColor = score >= 90 ? 'success' : score >= 70 ? 'warning' : 'exception'

  // 字段类型选项
  const typeOptions = [
    { value: 'id', label: 'ID' },
    { value: 'datetime', label: '日期时间' },
    { value: 'integer', label: '整数' },
    { value: 'float', label: '浮点数' },
    { value: 'boolean', label: '布尔' },
    { value: 'categorical', label: '分类' },
    { value: 'string', label: '字符串' },
    { value: 'text', label: '长文本' }
  ]

  // 字段表格列
  const profileColumns = [
    {
      title: '字段名',
      dataIndex: 'column',
      key: 'column'
    },
    {
      title: '推断类型',
      dataIndex: 'inferred_type',
      key: 'inferred_type',
      render: (type: string, record: ProfileField) => (
        <Select
          value={editedTypes[record.column] || type}
          onChange={(value) => setEditedTypes({ ...editedTypes, [record.column]: value })}
          style={{ width: 120 }}
          size="small"
        >
          {typeOptions.map(opt => (
            <Option key={opt.value} value={opt.value}>{opt.label}</Option>
          ))}
        </Select>
      )
    },
    {
      title: '缺失率',
      dataIndex: 'null_rate',
      key: 'null_rate',
      render: (rate: number) => (
        <Tag color={rate > 0.05 ? 'error' : rate > 0 ? 'warning' : 'success'}>
          {(rate * 100).toFixed(1)}%
        </Tag>
      )
    },
    {
      title: '基数',
      dataIndex: 'cardinality',
      key: 'cardinality',
      render: (card: number) => card.toLocaleString()
    }
  ]

  // 问题分级颜色
  const getSeverityColor = (severity: string) => {
    return severity === 'blocking' ? 'error' : 'warning'
  }

  // 问题类型标签
  const getIssueTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      null: '空值',
      format: '格式',
      unique: '唯一',
      range: '范围',
      logic: '逻辑',
      code: '码值'
    }
    return labels[type] || type
  }

  if (!data) return null

  return (
    <div className="quality-page">
      <Title level={2}>数据质检</Title>
      
      {/* 质量分卡片 */}
      <Card className="score-card">
        <div className="score-section">
          <div className="score-ring">
            <Progress
              type="circle"
              percent={score}
              strokeColor={scoreColor}
              format={(percent) => (
                <div className="score-text">
                  <div className="score-value">{percent}</div>
                  <div className="score-label">质量分</div>
                </div>
              )}
            />
          </div>
          <div className="score-info">
            <Space direction="vertical">
              <Text>总行数: <strong>{data.total_rows.toLocaleString()}</strong></Text>
              <Text>总列数: <strong>{data.column_count}</strong></Text>
              <Text>数据粒度: <Tag color="blue">{data.grain.grain_desc}</Tag></Text>
              <Space>
                <Tag color="error">必拦: {data.summary.blocking_count}</Tag>
                <Tag color="warning">提示: {data.summary.warning_count}</Tag>
              </Space>
            </Space>
          </div>
        </div>
        
        {!data.summary.can_proceed && (
          <Alert
            message="存在必拦项，需修复后才能生成看板"
            type="error"
            showIcon
            style={{ marginTop: 16 }}
          />
        )}
      </Card>

      {/* 字段信息表格 */}
      <Card title="字段信息" className="profile-card" style={{ marginTop: 24 }}>
        <Table
          columns={profileColumns}
          dataSource={data.profiles}
          rowKey="column"
          pagination={false}
          size="small"
        />
      </Card>

      {/* 问题清单 */}
      <Card title="质量问题清单" className="issues-card" style={{ marginTop: 24 }}>
        <List
          dataSource={data.issues}
          renderItem={issue => (
            <List.Item
              className={`issue-item ${issue.severity}`}
              actions={[
                <Tag color={getSeverityColor(issue.severity)}>
                  {issue.severity === 'blocking' ? '必拦' : '提示'}
                </Tag>
              ]}
            >
              <List.Item.Meta
                avatar={
                  issue.severity === 'blocking' ? 
                    <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 20 }} /> :
                    <WarningOutlined style={{ color: '#faad14', fontSize: 20 }} />
                }
                title={
                  <Space>
                    <Tag>{getIssueTypeLabel(issue.type)}</Tag>
                    <Text strong>{issue.column}</Text>
                    <Text type="secondary">{issue.row_count} 行</Text>
                  </Space>
                }
                description={
                  <div>
                    <Text>{issue.message}</Text>
                    {issue.sample_values.length > 0 && (
                      <div className="sample-values">
                        <Text type="danger" className="red-text">
                          异常样本: {issue.sample_values.join(', ')}
                        </Text>
                      </div>
                    )}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      {/* 操作按钮 */}
      <div className="action-bar" style={{ marginTop: 24, textAlign: 'right' }}>
        <Button icon={<ReloadOutlined />} onClick={loadQualityData} style={{ marginRight: 8 }}>
          重新质检
        </Button>
        <Button type="primary" disabled={!data.summary.can_proceed}>
          生成看板
        </Button>
      </div>
    </div>
  )
}
