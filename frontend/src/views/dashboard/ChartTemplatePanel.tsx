/**
 * night14 Task B 图表模板库前端面板
 * 浏览后端预置（8 业务域）与用户自建的图表模板，提供「一键套用」入口。
 * 套用走后端 /chart-templates/{id}/apply（复用 executor._execute_add_chart 渲染链，
 * 命中真实字段才新增、命不中跳过，不臆造垃圾图），前端仅负责把返回的 render_updates
 * 合并进当前看板 config（与 DashboardPage.handleAction 的 add_chart 合并逻辑一致）。
 */
import { useState, useEffect } from 'react'
import { Modal, Card, Tag, Select, Empty, Button, Spin, message, Space } from 'antd'
import { AppstoreOutlined } from '@ant-design/icons'
import { http } from '../../utils/request'

interface TemplateItem {
  id: string
  name: string
  category: string
  description?: string
  tags?: string[]
  config_json?: { charts?: any[] }
  usage_count?: number
}

interface ChartTemplatePanelProps {
  open: boolean
  onClose: () => void
  dashboardId?: string
  /** 套用成功后由父组件合并 render_updates 到看板 config 并提示 */
  onApplied: (res: any) => void
}

export default function ChartTemplatePanel({ open, onClose, dashboardId, onApplied }: ChartTemplatePanelProps) {
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<TemplateItem[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [cat, setCat] = useState<string | undefined>(undefined)
  const [applyingId, setApplyingId] = useState<string | null>(null)

  // 打开时拉取模板列表（一次性拉全，前端做业务域过滤）
  useEffect(() => {
    if (!open) return
    let mounted = true
    setLoading(true)
    http
      .get<any>('/chart-templates/list', { page: 1, page_size: 100 })
      .then((res) => {
        if (!mounted) return
        const list: TemplateItem[] = res.items || []
        setItems(list)
        const cats = Array.from(new Set(list.map((t) => t.category).filter(Boolean))) as string[]
        setCategories(cats)
      })
      .catch((err) => message.error(`加载模板库失败: ${err?.message || '网络错误'}`))
      .finally(() => mounted && setLoading(false))
    return () => {
      mounted = false
    }
  }, [open])

  const filtered = cat ? items.filter((t) => t.category === cat) : items

  const apply = async (tpl: TemplateItem) => {
    if (!dashboardId) {
      message.warning('当前看板无有效 ID，无法套用')
      return
    }
    setApplyingId(tpl.id)
    try {
      const res = await http.post<any>(`/chart-templates/${tpl.id}/apply`, { dashboard_id: dashboardId })
      if (res?.success) {
        onApplied(res)
      } else {
        message.error(res?.message || '套用失败')
      }
    } catch (err: any) {
      message.error(`套用失败: ${err?.message || '网络错误'}`)
    } finally {
      setApplyingId(null)
    }
  }

  return (
    <Modal title="图表模板库" open={open} onCancel={onClose} footer={null} width={760}>
      <div style={{ marginBottom: 12 }}>
        <Space>
          <span>业务域：</span>
          <Select
            allowClear
            placeholder="全部业务域"
            style={{ width: 200 }}
            value={cat}
            onChange={setCat}
            options={categories.map((c) => ({ value: c, label: c }))}
          />
          <span style={{ color: 'rgba(0,0,0,.45)', fontSize: 12 }}>共 {filtered.length} 个模板</span>
        </Space>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin tip="加载模板库..." />
        </div>
      ) : filtered.length === 0 ? (
        <Empty description="暂无模板" />
      ) : (
        <div style={{ maxHeight: 460, overflowY: 'auto' }}>
          {filtered.map((tpl) => (
            <Card
              key={tpl.id}
              size="small"
              style={{ marginBottom: 12 }}
              title={
                <span>
                  <Tag color="blue">{tpl.category}</Tag>
                  {tpl.name}
                </span>
              }
            >
              <div style={{ marginBottom: 8, color: 'rgba(0,0,0,.65)' }}>{tpl.description || '—'}</div>
              <Space size={4} wrap style={{ marginBottom: 8 }}>
                {(tpl.tags || []).map((tg) => (
                  <Tag key={tg}>{tg}</Tag>
                ))}
                <Tag>{(tpl.config_json?.charts || []).length} 图</Tag>
                <Tag>已套用 {tpl.usage_count || 0} 次</Tag>
              </Space>
              <div>
                <Button
                  type="primary"
                  icon={<AppstoreOutlined />}
                  loading={applyingId === tpl.id}
                  onClick={() => apply(tpl)}
                >
                  一键套用
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </Modal>
  )
}
