import { useState } from 'react'
import { Modal, Radio, Alert, Space, Typography, Tag, Table } from 'antd'

const { Text } = Typography

interface EncodingOption {
  value: string
  label: string
  description: string
}

const ENCODING_OPTIONS: EncodingOption[] = [
  { value: 'utf-8', label: 'UTF-8', description: '国际通用编码，推荐首选' },
  { value: 'gbk', label: 'GBK', description: '简体中文Windows默认编码' },
  { value: 'gb18030', label: 'GB18030', description: '国家标准编码，兼容GBK' },
  { value: 'big5', label: 'Big5', description: '繁体中文编码' }
]

interface EncodingSelectModalProps {
  visible: boolean
  fileId: string
  fileName: string
  detectedEncoding: string
  confidence: number
  needsSelection: boolean
  previewData?: {
    columns: string[]
    rows: any[][]
    total_rows: number
  }
  onCancel: () => void
  onConfirm: (encoding: string) => void
}

export default function EncodingSelectModal({
  visible,
  fileId,
  fileName,
  detectedEncoding,
  confidence,
  needsSelection,
  previewData,
  onCancel,
  onConfirm
}: EncodingSelectModalProps) {
  const [selectedEncoding, setSelectedEncoding] = useState<string>(
    needsSelection ? 'utf-8' : detectedEncoding
  )

  return (
    <Modal
      title="选择文件编码"
      open={visible}
      onCancel={onCancel}
      onOk={() => onConfirm(selectedEncoding)}
      width={600}
      okText="确认"
      cancelText="取消"
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">系统检测到以下编码，请选择正确的编码格式：</Text>
        <br />
        <Text strong>{fileName}</Text>
      </div>

      {/* 自动检测结果 */}
      {confidence > 0 && (
        <Alert
          message={
            <Space>
              <Text>自动检测编码：</Text>
              <Tag color={confidence >= 0.7 ? 'success' : 'warning'}>
                {detectedEncoding.toUpperCase()}
              </Tag>
              <Text type="secondary">
                (置信度: {(confidence * 100).toFixed(1)}%)
              </Text>
            </Space>
          }
          type={confidence >= 0.7 ? 'success' : 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {needsSelection && (
        <Alert
          message="编码置信度较低，建议手动选择正确的编码格式"
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 编码选项 */}
      <div style={{ marginBottom: 16 }}>
        <Text strong>选择编码：</Text>
        <Radio.Group
          value={selectedEncoding}
          onChange={(e) => setSelectedEncoding(e.target.value)}
          style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}
        >
          {ENCODING_OPTIONS.map((enc) => (
            <Radio key={enc.value} value={enc.value}>
              <Space>
                <Text>{enc.label}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {enc.description}
                </Text>
                {enc.value === detectedEncoding && confidence >= 0.7 && (
                  <Tag color="blue">推荐</Tag>
                )}
              </Space>
            </Radio>
          ))}
        </Radio.Group>
      </div>

      {/* 预览表格 */}
      {previewData && (
        <div style={{ marginTop: 16 }}>
          <Text strong>数据预览（前5行）：</Text>
          <Table
            dataSource={previewData.rows.map((row, idx) => ({
              key: idx,
              ...previewData.columns.reduce((acc, col, i) => {
                acc[col] = row[i]
                return acc
              }, {} as any)
            }))}
            columns={previewData.columns.slice(0, 5).map(col => ({
              title: col,
              dataIndex: col,
              ellipsis: true
            }))}
            size="small"
            pagination={false}
            scroll={{ x: 'max-content' }}
            style={{ marginTop: 8 }}
          />
        </div>
      )}

      <div style={{ marginTop: 16, padding: 12, background: '#f5f5f5', borderRadius: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          💡 提示：如果预览数据显示乱码，请尝试选择其他编码格式。
          <br />
          常见情况：Windows导出的CSV通常为 GBK 编码，Mac/Linux 通常为 UTF-8。
        </Text>
      </div>
    </Modal>
  )
}
