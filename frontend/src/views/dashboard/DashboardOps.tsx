import { useState, useEffect, useCallback } from 'react'
import {
  Button, Dropdown, Modal, Radio, Input, Switch, Tag, List, Drawer, message, Space, Divider, Empty, Select, Segmented, Tooltip, Breadcrumb, Spin,
} from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeftOutlined, EditOutlined, ShareAltOutlined, ExportOutlined, HistoryOutlined,
  ApartmentOutlined, DeleteOutlined, MoreOutlined, CopyOutlined, DownloadOutlined, RollbackOutlined, CheckOutlined, FileTextOutlined,
} from '@ant-design/icons'

import './DashboardOps.css'
import { http } from '../../utils/request'

interface DashboardOpsProps {
  id?: string
  title: string
  onRename?: (next: string) => void
  onDelete?: () => void
  generationMode?: 'ai' | 'rule' | string  // 问题1：看板生成方式（绿标/灰标）
}

interface VersionItem {
  key: string
  id: string
  label: string
  time: string
  by: string
  diff: string
  current: boolean
}

interface ShareResult {
  share_id: string
  share_code: string
  share_url: string
  permission: string
  expires_at: string
  qr_code: string
}

const mockHistory = [
  { id: 'h1', title: '各区域逾期率变化趋势', time: '今天 15:12', summary: '关于华东地区逾期率连续三月升高的归因分析' },
  { id: 'h2', title: '担保类型结构调整建议', time: '今天 14:40', summary: '对比信用与抵押担保的额度分布并提出调整建议' },
  { id: 'h3', title: '大额担保客户风险画像', time: '昨天 11:03', summary: '筛选单笔担保金额超过 3000 万的客户明细' },
  { id: 'h4', title: '季度不良率目标达成', time: '08-10 09:22', summary: '按季度拆解不良率目标与实际达成对比' },
]

export default function DashboardOps({ id, title, onRename, onDelete, generationMode }: DashboardOpsProps) {
  const nav = useNavigate()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(title)

  const [shareOpen, setShareOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [versionOpen, setVersionOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteText, setDeleteText] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)

  // 分享
  const [viewPerm, setViewPerm] = useState('login')
  const [editPerm, setEditPerm] = useState('owner')
  const [expire, setExpire] = useState('7')
  const [usePwd, setUsePwd] = useState(false)
  const [pwd, setPwd] = useState('')
  const [link, setLink] = useState('')
  const [genLoading, setGenLoading] = useState(false)
  // 导出
  const [fmt, setFmt] = useState('pdf')
  const [scope, setScope] = useState('all')
  const [inclData, setInclData] = useState(true)
  const [inclNote, setInclNote] = useState(true)
  const [exportLoading, setExportLoading] = useState(false)
  // 版本
  const [versions, setVersions] = useState<VersionItem[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  // 历史
  const [hkw, setHkw] = useState('')
  const [hRange, setHRange] = useState('all')

  // 打开版本抽屉时从后端加载版本列表
  useEffect(() => {
    if (!versionOpen) return
    if (!id) {
      setVersions([])
      return
    }
    let mounted = true
    setVersionsLoading(true)
    http
      .get<any>(`/versions/list/${id}`)
      .then((res) => {
        if (!mounted) return
        const list: VersionItem[] = (res.versions || []).map((v: any, i: number) => ({
          key: v.id || `${i}`,
          id: v.id,
          label: `v${v.number}`,
          time: v.created_at ? new Date(v.created_at).toLocaleString('zh-CN') : '',
          by: v.created_by || '匿名',
          diff: v.description || v.name || '版本记录',
          current: false,
        }))
        // 后缀最高的版本标记为当前
        if (list.length) list[list.length - 1].current = true
        setVersions(list)
      })
      .catch((err) => message.error(`加载版本失败: ${err?.message || '网络错误'}`))
      .finally(() => mounted && setVersionsLoading(false))
    return () => { mounted = false }
  }, [versionOpen, id])

  // 生成分享链接 → 真实后端
  const genLink = async () => {
    if (!id) {
      message.warning('当前看板无有效 ID，无法生成分享链接')
      return
    }
    setGenLoading(true)
    try {
      const permission = editPerm === 'login' ? 'edit' : 'view'
      const expires = expire === '0' ? 3650 : Number(expire)
      const res = await http.post<ShareResult>('/shares/create', {
        dashboard_id: id,
        permission,
        expires_days: expires,
        password: usePwd ? pwd : null,
      })
      const url = res.share_url || `${window.location.origin}/s/${res.share_code}`
      setLink(url)
      message.success('分享链接已生成')
    } catch (err: any) {
      message.error(`生成分享链接失败: ${err?.message || '网络错误'}`)
    } finally {
      setGenLoading(false)
    }
  }
  const copyLink = async () => {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      message.success('链接已复制')
    } catch {
      message.success('链接已复制')
    }
  }

  // 导出 → 真实后端（JSON 真实内容；PDF/Excel/PNG 依赖后端返回的下载地址）
  const doExport = async () => {
    if (!id) {
      message.warning('当前看板无有效 ID，无法导出')
      return
    }
    const formatMap: Record<string, string> = { pdf: 'pdf', excel: 'excel', png: 'png', json: 'json' }
    setExportLoading(true)
    try {
      const res = await http.post<any>('/exports/sync', {
        dashboard_id: id,
        format: formatMap[fmt] || 'pdf',
        include_watermark: true,
        include_logic: inclNote,
        include_data: inclData,
      })

      if (fmt === 'json' && res?.content) {
        // JSON：真实触发浏览器下载
        const blob = new Blob([JSON.stringify(res.content, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = res.filename || `${title}.dashboard.json`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        message.success('JSON 已导出下载')
        setExportOpen(false)
        return
      }

      if (res?.mode === 'async') {
        message.success('导出任务已创建，将通知（演示）')
      } else if (res?.download_url) {
        message.success('导出完成，文件已生成')
        if (res.download_url.startsWith('/') || res.download_url.startsWith('http')) {
          window.open(res.download_url, '_blank')
        }
      } else {
        message.success('导出完成')
      }
    } catch (err: any) {
      message.error(`导出失败: ${err?.message || '网络错误'}`)
    } finally {
      setExportLoading(false)
    }
  }

  const previewVersion = (v: string) => message.info(`预览版本 ${v}（演示）`)
  const rollback = async (ver: VersionItem) => {
    if (!id) return
    message.loading({ content: '正在回退...', key: 'rollback' })
    try {
      await http.post('/versions/rollback/' + id, { version_id: ver.id })
      message.success({ content: `已回退到 ${ver.label}`, key: 'rollback' })
      setVersionOpen(false)
    } catch (err: any) {
      message.error({ content: `回退失败: ${err?.message || '网络错误'}`, key: 'rollback' })
    }
  }
  const compare = (a: string, b: string) => message.info(`对比 ${a} 与 ${b}（演示）`)

  const commitRename = async () => {
    const next = draft.trim()
    if (!next || next === title) {
      setEditing(false)
      return
    }
    if (id) {
      try {
        await http.patch(`/dashboards/${id}`, { name: next })
        onRename?.(next)
        setDraft(next)
        message.success('标题已保存')
      } catch (err: any) {
        message.error(`保存标题失败: ${err?.message || '网络错误'}`)
        setDraft(title)
      }
    } else {
      onRename?.(next)
    }
    setEditing(false)
  }

  const confirmDelete = async () => {
    if (!id) {
      message.warning('看板 ID 缺失')
      return
    }
    try {
      setDeleteLoading(true)
      await http.delete(`/dashboards/${id}`, { confirm_name: deleteText })
      message.success('看板已删除')
      setDeleteOpen(false)
      onDelete?.()
      nav('/dashboards')
    } catch (err: any) {
      message.error(`删除失败: ${err?.message || '网络错误'}`)
    } finally {
      setDeleteLoading(false)
    }
  }

  // 操作菜单仅收纳低频项（对话历史/删除）；编辑/分享/导出/版本/血缘全部平铺（2026-09-18 对齐原型）
  const menuItems = {
    items: [
      { key: 'history', icon: <HistoryOutlined />, label: '对话历史' },
      { type: 'divider' as const },
      { key: 'delete', icon: <DeleteOutlined />, label: '删除看板', danger: true },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'history') setHistoryOpen(true)
      else if (key === 'delete') { setDeleteText(''); setDeleteOpen(true) }
    },
  }

  const versionList = versions.map(v => ({
    ...v,
    actions: (
      <Space size={4}>
        <Tooltip title="预览"><Button size="small" icon={<CheckOutlined />} onClick={() => previewVersion(v.label)} /></Tooltip>
        <Tooltip title="回退"><Button size="small" icon={<RollbackOutlined />} disabled={v.current} onClick={() => rollback(v)} /></Tooltip>
        <Tooltip title="对比"><Button size="small" onClick={() => compare('v1', v.label)} disabled={v.current}>对比</Button></Tooltip>
      </Space>
    ),
  }))

  const historyFiltered = mockHistory.filter(h => {
    const kwOk = !hkw || h.title.includes(hkw) || h.summary.includes(hkw)
    const rangeOk = hRange === 'all' || (hRange === 'today' && h.time.startsWith('今天'))
    return kwOk && rangeOk
  })

  return (
    <div className="dash-ops">
      {/* 第一行：页面索引（独立成行，与看板内容区分） */}
      <div className="dash-ops-crumb">
        <Breadcrumb
          items={[
            { title: <a onClick={() => nav('/dashboards')}>我的看板</a> },
            { title: title },
          ]}
        />
      </div>

      {/* 第二行：看板标题 + 操作按钮 */}
      <div className="dash-ops-row">
        {editing ? (
          <Input
            className="dash-ops-title-input"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onPressEnter={commitRename}
            onBlur={commitRename}
            autoFocus
            suffix={<Tag color="blue">回车保存</Tag>}
          />
        ) : (
          <Tooltip title="点击编辑标题">
            <h1 className="dash-ops-title" onClick={() => { setDraft(title); setEditing(true) }}>
              {title} <EditOutlined className="dash-ops-title-edit" />
              {/* 问题1修复：生成方式徽标——绿标「AI 生成」/ 灰标「本次为规则生成」 */}
              {generationMode === 'ai' && (
                <Tag color="green" style={{ marginLeft: 8, fontSize: 12, verticalAlign: 'middle' }}>AI 生成</Tag>
              )}
              {generationMode === 'rule' && (
                <Tag color="default" style={{ marginLeft: 8, fontSize: 12, verticalAlign: 'middle' }}>本次为规则生成</Tag>
              )}
            </h1>
          </Tooltip>
        )}

        <div className="dash-ops-spacer" />

        <Space size={4}>
          {/* 全部平铺（对齐原型：编辑/分享/导出/版本/血缘 直出，不再折叠进"操作"下拉） */}
          <Button icon={<EditOutlined />} onClick={() => { setDraft(title); setEditing(true) }}>编辑</Button>
          <Button icon={<ShareAltOutlined />} onClick={() => setShareOpen(true)}>分享</Button>
          <Button icon={<ExportOutlined />} onClick={() => setExportOpen(true)}>导出</Button>
          <Button icon={<HistoryOutlined />} onClick={() => setVersionOpen(true)}>版本</Button>
          <Button
            icon={<ApartmentOutlined />}
            onClick={() => nav(`/lineage?dashboard_id=${id || ''}&from=/dashboard`)}
          >
            血缘
          </Button>
          <Button icon={<FileTextOutlined />} onClick={() => id && nav(`/report?report_id=&dashboard_id=${id}`)}>报告</Button>
          <Dropdown menu={menuItems} trigger={['click']}>
            <Button icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      </div>

      {/* C02 分享看板 */}
      <Modal title="分享看板" open={shareOpen} onCancel={() => setShareOpen(false)} footer={null} width={520}>
        <Divider style={{ marginTop: 0 }} />
        <div>
          <div style={{ marginBottom: 12 }}><b>查看权限</b>
            <Radio.Group value={viewPerm} onChange={e => setViewPerm(e.target.value)} style={{ display: 'block', marginTop: 8 }}>
              <Radio value="login">仅登录用户可查看</Radio>
              <Radio value="any">任何人凭链接可查看</Radio>
            </Radio.Group>
          </div>
          <div style={{ marginBottom: 12 }}><b>编辑权限</b>
            <Radio.Group value={editPerm} onChange={e => setEditPerm(e.target.value)} style={{ display: 'block', marginTop: 8 }}>
              <Radio value="owner">仅自己可编辑</Radio>
              <Radio value="login">登录用户可编辑</Radio>
            </Radio.Group>
          </div>
          <div style={{ marginBottom: 12 }}><b>有效期</b>
            <Segmented style={{ marginTop: 8 }} value={expire} onChange={setExpire as any}
              options={[{ label: '1天', value: '1' }, { label: '7天', value: '7' }, { label: '30天', value: '30' }, { label: '永久', value: '0' }]} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <b>密码保护</b>
              <Switch checked={usePwd} onChange={setUsePwd} />
              {usePwd && <Input.Password placeholder="访问密码" style={{ width: 180 }} value={pwd} onChange={e => setPwd(e.target.value)} />}
            </Space>
          </div>
          {link ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <Input value={link} readOnly />
              <Button icon={<CopyOutlined />} onClick={copyLink}>复制</Button>
              <Button onClick={() => message.info('二维码（演示）')}>二维码</Button>
            </div>
          ) : (
            <Button type="primary" onClick={genLink} loading={genLoading}>生成分享链接</Button>
          )}
        </div>
      </Modal>

      {/* C03 导出看板 */}
      <Modal title="导出看板" open={exportOpen} onCancel={() => setExportOpen(false)}
        footer={[<Button key="c" onClick={() => setExportOpen(false)}>取消</Button>, <Button key="o" type="primary" onClick={doExport} icon={<DownloadOutlined />} loading={exportLoading}>确认导出</Button>]}
        width={500}>
        <Divider style={{ marginTop: 0 }} />
        <div style={{ marginBottom: 12 }}><b>导出格式</b>
          <Radio.Group value={fmt} onChange={e => setFmt(e.target.value)} style={{ display: 'block', marginTop: 8 }}>
            <Radio value="pdf">PDF 文档</Radio>
            <Radio value="excel">Excel 文件</Radio>
            <Radio value="png">图片 PNG</Radio>
            <Radio value="json">数据 JSON</Radio>
          </Radio.Group>
        </div>
        <div style={{ marginBottom: 12 }}><b>导出范围</b>
          <Radio.Group value={scope} onChange={e => setScope(e.target.value)} style={{ display: 'block', marginTop: 8 }}>
            <Radio value="all">全部图表</Radio>
            <Radio value="current">当前图表</Radio>
            <Radio value="custom">自定义选择</Radio>
          </Radio.Group>
        </div>
        <Space size={20}>
          <Space><Switch checked={inclData} onChange={setInclData} size="small" /> 包含数据</Space>
          <Space><Switch checked={inclNote} onChange={setInclNote} size="small" /> 包含分析说明</Space>
        </Space>
      </Modal>

      {/* C04 版本管理 */}
      <Drawer title="版本管理" open={versionOpen} onClose={() => setVersionOpen(false)} width={480}>
        {versionsLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="加载版本..." /></div>
        ) : (
          <List
            dataSource={versionList}
            locale={{ emptyText: <Empty description="暂无版本记录" /> }}
            renderItem={v => (
              <List.Item key={v.key}
                extra={v.current ? <Tag color="blue">当前</Tag> : v.actions}
                style={{ alignItems: 'flex-start' }}>
                <List.Item.Meta
                  title={<span>{v.label} · {v.by}</span>}
                  description={<>
                    <div style={{ color: 'rgba(0,0,0,.45)' }}>{v.time}</div>
                    <div style={{ marginTop: 4 }}>{v.diff}</div>
                  </>}
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>

      {/* C06 对话历史 */}
      <Modal title="对话历史" open={historyOpen} onCancel={() => setHistoryOpen(false)} footer={null} width={560}>
        <Space style={{ marginBottom: 12, width: '100%' }}>
          <Input placeholder="搜索历史对话" value={hkw} onChange={e => setHkw(e.target.value)} allowClear style={{ flex: 1 }} />
          <Select value={hRange} onChange={setHRange} style={{ width: 130 }}
            options={[{ value: 'all', label: '全部时间' }, { value: 'today', label: '今天' }, { value: 'week', label: '本周' }]} />
        </Space>
        <List
          dataSource={historyFiltered}
          locale={{ emptyText: <Empty description="无匹配对话" /> }}
          renderItem={h => (
            <List.Item actions={[<Button key="d" size="small" type="text" danger onClick={() => message.success('已删除')}>删除</Button>, <Button key="e" size="small" type="text" onClick={() => message.info('导出对话（演示）')}>导出</Button>]}>
              <List.Item.Meta title={h.title} description={<><div style={{ color: 'rgba(0,0,0,.45)' }}>{h.time}</div>{h.summary}</>} />
            </List.Item>
          )}
        />
      </Modal>

      {/* D04 删除确认 */}
      <Modal title="删除看板" open={deleteOpen} onCancel={() => setDeleteOpen(false)}
        okText="确认删除" okButtonProps={{ danger: true, disabled: deleteText !== title }}
        confirmLoading={deleteLoading}
        onOk={confirmDelete}>
        <div style={{ color: '#ff4d4f', marginBottom: 12 }}>删除后将同时移除：图表、版本记录、分享链接，且不可恢复。</div>
        <div style={{ marginBottom: 8 }}>请输入看板名称 <b>「{title}」</b> 以确认：</div>
        <Input value={deleteText} onChange={e => setDeleteText(e.target.value)} placeholder={title} />
      </Modal>
    </div>
  )
}