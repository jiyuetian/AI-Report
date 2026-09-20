import { useState } from 'react'
import { Modal, Radio, Table, Tag, Space, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

const { Text } = Typography

interface SheetInfo {
  index: number
  name: string
  row_count: number
  col_count: number
  headers: string[]
}

interface SheetSelectModalProps {
  visible: boolean
  fileId: string
  fileName: string
  sheets: SheetInfo[]
  onCancel: () => void
  onConfirm: (sheetName: string) => void
}

export default function SheetSelectModal({
  visible,
  fileId,
  fileName,
  sheets,
  onCancel,
  onConfirm
}: SheetSelectModalProps) {
  const [selectedSheet, setSelectedSheet] = useState<string>(
    sheets.length > 0 ? sheets[0].name : ''
  )

  const columns: ColumnsType<SheetInfo> = [
    {
      title: '选择',
      dataIndex: 'index',
      width: 60,
      render: (_, record) => (
        <Radio
          checked={selectedSheet === record.name}
          onChange={() => setSelectedSheet(record.name)}
        />
      )
    },
    {
      title: 'Sheet名称',
      dataIndex: 'name',
      render: (name, record) => (
        <Space>
          <Text strong>{name}</Text>
          {record.index === 0 && <Tag color="blue">默认</Tag>}
        </Space>
      )
    },
    {
      title: '行数',
      dataIndex: 'row_count',
      width: 100,
      render: (count) => `${count.toLocaleString()} 行`
    },
    {
      title: '列数',
      dataIndex: 'col_count',
      width: 100,
      render: (count) => `${count} 列`
    },
    {
      title: '列名预览',
      dataIndex: 'headers',
      ellipsis: true,
      render: (headers: string[]) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {headers.slice(0, 5).join(', ')}
          {headers.length > 5 && '...'}
        </Text>
      )
    }
  ]

  return (
    <Modal
      title="选择工作表"
      open={visible}
      onCancel={onCancel}
      onOk={() => onConfirm(selectedSheet)}
      width={700}
      okText="确认"
      cancelText="取消"
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">检测到文件包含多个工作表，请选择要导入的工作表：</Text>
        <br />
        <Text strong>{fileName}</Text>
      </div>

      <Table
        columns={columns}
        dataSource={sheets}
        rowKey="name"
        pagination={false}
        size="small"
        bordered
      />

      <div style={{ marginTop: 16, padding: 12, background: '#f5f5f5', borderRadius: 6 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          💡 提示：选择工作表后，系统将预览前5行数据供您确认。
        </Text>
      </div>
    </Modal>
  )
}
