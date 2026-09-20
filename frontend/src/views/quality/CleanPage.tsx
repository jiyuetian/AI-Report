import { useState, useEffect } from 'react'
import { Card, Steps, Button, Table, Tag, Progress, Alert, Space, Typography, Radio, List, message } from 'antd'
import { CheckCircleOutlined, LoadingOutlined, CloseCircleOutlined, UndoOutlined } from '@ant-design/icons'
import './CleanPage.css'

const { Title, Text } = Typography
const { Step } = Steps

interface CleanRule {
  rule_id: string
  issue_type: string
  column: string
  strategy: string
  status: 'running' | 'success' | 'failed'
  progress: number
}

interface CleanPageProps {
  datasetId: string
}

export default function CleanPage({ datasetId }: CleanPageProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [rules, setRules] = useState<CleanRule[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<Record<string, string>>({})

  // 修复策略选项
  const strategies: Record<string, { value: string; label: string; desc: string }[]> = {
    null: [
      { value: 'fill_median', label: '中位数填充', desc: '按分组计算中位数填充空值' },
      { value: 'delete', label: '删除空值行', desc: '删除包含空值的整行' },
      { value: 'mark', label: '标记空值', desc: '标记但不删除数据' }
    ],
    format: [
      { value: 'convert_format', label: '格式转换', desc: '统一转换为标准格式' },
      { value: 'delete', label: '删除异常行', desc: '删除格式异常的行' }
    ],
    unique: [
      { value: 'deduplicate', label: '去重', desc: '删除重复行，保留首次出现' }
    ],
    range: [
      { value: 'truncate', label: '截断', desc: '将超出范围的值截断到阈值' },
      { value: 'mark', label: '标记', desc: '标记异常值' }
    ],
    logic: [
      { value: 'mark', label: '标记', desc: '标记逻辑错误的数据' }
    ],
    code: [
      { value: 'mark', label: '标记', desc: '标记不规范码值' }
    ]
  }

  // 模拟加载待修复问题
  useEffect(() => {
    const mockRules: CleanRule[] = [
      { rule_id: '1', issue_type: 'null', column: '借据编号', strategy: '', status: 'running', progress: 0 },
      { rule_id: '2', issue_type: 'format', column: '放款日期', strategy: '', status: 'running', progress: 0 },
      { rule_id: '3', issue_type: 'unique', column: '借据编号', strategy: '', status: 'running', progress: 0 },
      { rule_id: '4', issue_type: 'range', column: '抵押率', strategy: '', status: 'running', progress: 0 }
    ]
    setRules(mockRules)
  }, [datasetId])

  // 一键采纳
  const handleAutoFix = async () => {
    setLoading(true)
    setCurrentStep(1) // 进入执行中

    // 模拟逐个执行修复
    for (let i = 0; i < rules.length; i++) {
      const rule = rules[i]
      
      // 更新为运行中
      updateRuleStatus(i, 'running', 0)
      
      // 模拟进度
      for (let p = 0; p <= 100; p += 20) {
        await new Promise(r => setTimeout(r, 200))
        updateRuleStatus(i, 'running', p)
      }
      
      // 完成
      updateRuleStatus(i, 'success', 100)
    }

    setCurrentStep(2) // 完成
    setLoading(false)
    message.success('修复完成')
  }

  // 逐项向导
  const handleFixOneByOne = async (index: number) => {
    const rule = rules[index]
    const strategy = selectedStrategy[`${rule.issue_type}_${rule.column}`]
    
    if (!strategy) {
      message.warning('请选择修复策略')
      return
    }

    updateRuleStatus(index, 'running', 0)
    
    // 模拟执行
    for (let p = 0; p <= 100; p += 25) {
      await new Promise(r => setTimeout(r, 300))
      updateRuleStatus(index, 'running', p)
    }
    
    updateRuleStatus(index, 'success', 100)
  }

  // 撤销修复
  const handleRollback = async (ruleId: string) => {
    // TODO: 调用撤销API
    message.success('已撤销')
  }

  const updateRuleStatus = (index: number, status: 'running' | 'success' | 'failed', progress: number) => {
    setRules(prev => prev.map((r, i) => 
      i === index ? { ...r, status, progress } : r
    ))
  }

  // 问题类型标签
  const getIssueTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      null: '空值', format: '格式', unique: '唯一',
      range: '范围', logic: '逻辑', code: '码值'
    }
    return labels[type] || type
  }

  // 必拦项检查
  const hasBlockingIssues = () => {
    return rules.some(r => ['null', 'format'].includes(r.issue_type))
  }

  // 是否可以忽略
  const canIgnore = (issueType: string) => {
    return !['null', 'format'].includes(issueType) // 必拦项不可忽略
  }

  return (
    <div className="clean-page">
      <Title level={2}>数据修复</Title>

      {/* 步骤条 */}
      <Steps current={currentStep} className="clean-steps">
        <Step title="选择策略" icon={currentStep === 0 ? <LoadingOutlined /> : undefined} />
        <Step title="执行修复" icon={currentStep === 1 ? <LoadingOutlined /> : undefined} />
        <Step title="完成" />
      </Steps>

      {/* 策略选择卡片 */}
      {currentStep === 0 && (
        <Card className="strategy-card" style={{ marginTop: 24 }}>
          <Alert
            message="必拦项（空值、格式）必须修复，不可忽略"
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <List
            dataSource={rules}
            renderItem={(rule, index) => (
              <List.Item className="strategy-item">
                <div className="strategy-header">
                  <Space>
                    <Tag color={['null', 'format'].includes(rule.issue_type) ? 'error' : 'warning'}>
                      {getIssueTypeLabel(rule.issue_type)}
                    </Tag>
                    <Text strong>{rule.column}</Text>
                  </Space>
                </div>

                <Radio.Group
                  value={selectedStrategy[`${rule.issue_type}_${rule.column}`]}
                  onChange={(e) => setSelectedStrategy({
                    ...selectedStrategy,
                    [`${rule.issue_type}_${rule.column}`]: e.target.value
                  })}
                  disabled={!canIgnore(rule.issue_type)}
                >
                  <Space direction="vertical">
                    {strategies[rule.issue_type]?.map(s => (
                      <Radio key={s.value} value={s.value}>
                        <Space>
                          <Text>{s.label}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>{s.desc}</Text>
                        </Space>
                      </Radio>
                    ))}
                    {canIgnore(rule.issue_type) && (
                      <Radio value="ignore">
                        <Text type="secondary">忽略（仅提示项可选）</Text>
                      </Radio>
                    )}
                  </Space>
                </Radio.Group>

                {currentStep === 0 && (
                  <Button 
                    size="small" 
                    onClick={() => handleFixOneByOne(index)}
                    style={{ marginTop: 8 }}
                  >
                    立即修复
                  </Button>
                )}
              </List.Item>
            )}
          />

          <div className="action-bar">
            <Button type="primary" onClick={handleAutoFix} loading={loading}>
              一键采纳全部
            </Button>
          </div>
        </Card>
      )}

      {/* 执行进度卡片 */}
      {currentStep === 1 && (
        <Card className="progress-card" style={{ marginTop: 24 }}>
          <Title level={4}>修复执行中...</Title>
          
          <List
            dataSource={rules}
            renderItem={rule => (
              <List.Item>
                <div style={{ width: '100%' }}>
                  <Space>
                    {rule.status === 'running' && <LoadingOutlined />}
                    {rule.status === 'success' && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                    {rule.status === 'failed' && <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                    <Tag>{getIssueTypeLabel(rule.issue_type)}</Tag>
                    <Text>{rule.column}</Text>
                    <Text type="secondary">
                      {rule.status === 'running' ? '修复中...' : 
                       rule.status === 'success' ? '完成' : '失败'}
                    </Text>
                  </Space>
                  <Progress 
                    percent={rule.progress} 
                    size="small" 
                    status={rule.status === 'failed' ? 'exception' : undefined}
                    style={{ marginTop: 8 }}
                  />
                </div>
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* 完成卡片 */}
      {currentStep === 2 && (
        <Card className="complete-card" style={{ marginTop: 24 }}>
          <div className="complete-header">
            <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />
            <Title level={3}>修复完成</Title>
            <Text type="secondary">所有问题已处理完毕</Text>
          </div>

          <Table
            dataSource={rules}
            columns={[
              { title: '类型', dataIndex: 'issue_type', render: (t: string) => <Tag>{getIssueTypeLabel(t)}</Tag> },
              { title: '字段', dataIndex: 'column' },
              { title: '策略', dataIndex: 'strategy' },
              { title: '状态', dataIndex: 'status', render: (s: string) => (
                s === 'success' ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>
              )},
              { 
                title: '操作', 
                render: (_, record) => (
                  <Button 
                    size="small" 
                    icon={<UndoOutlined />}
                    onClick={() => handleRollback(record.rule_id)}
                  >
                    撤销
                  </Button>
                )
              }
            ]}
            rowKey="rule_id"
            pagination={false}
            size="small"
          />

          <div className="action-bar">
            <Button type="primary" onClick={() => window.location.href = `/quality/${datasetId}`}>
              查看质检结果
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
