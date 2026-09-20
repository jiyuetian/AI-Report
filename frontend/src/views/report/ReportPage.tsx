/**
 * 报告查看页 - 7章节图文报告展示 + 历史版本回看
 */
import { useEffect, useState } from 'react'
import { Spin, Alert, Button, Drawer, Tag, Tooltip, Empty } from 'antd'
import { ArrowLeftOutlined, DownloadOutlined, ReloadOutlined, HistoryOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { http } from '../../utils/request'
import './ReportPage.css'

interface ReportData {
  title: string
  generated_at: string
  llm_used: boolean
  chart_count: number
  chapters: Array<{
    number: number
    title: string
    content: string
    charts: any[]
  }>
}

interface ReportVersion {
  report_id: string
  version_id: string
  title: string
  llm_used: boolean
  chart_count: number
  generated_at: string
}

export default function ReportPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const reportId = searchParams.get('report_id')
  const dashboardId = searchParams.get('dashboard_id')

  const [loading, setLoading] = useState(true)
  const [reportData, setReportData] = useState<ReportData | null>(null)
  const [htmlContent, setHtmlContent] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [versions, setVersions] = useState<ReportVersion[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // 生成报告
  const handleGenerate = async () => {
    if (!dashboardId) return
    setLoading(true)
    setError('')
    try {
      const resp = await http.post('/api/v1/reports', {
        dashboard_id: dashboardId,
        force_regenerate: true,
      })
      const rid = resp.report_id
      window.location.href = `/report?report_id=${rid}&dashboard_id=${dashboardId}`
    } catch (e: any) {
      setError(e.response?.data?.detail || '报告生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 加载报告
  useEffect(() => {
    if (!reportId) {
      // 无 report_id（如从看板"生成报告"入口进入）：直接展示空态，避免永远 loading
      setLoading(false)
      return
    }
    ;(async () => {
      try {
        const [jsonResp, htmlResp] = await Promise.all([
          http.get(`/api/v1/reports/${reportId}/json`),
          http.get(`/api/v1/reports/${reportId}/html`),
        ])
        setReportData(jsonResp.data)
        setHtmlContent(htmlResp)
      } catch (e: any) {
        setError(e.response?.data?.detail || '报告加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [reportId])

  // 加载历史版本列表
  const loadVersions = async () => {
    if (!dashboardId) return
    setHistoryLoading(true)
    try {
      const resp = await http.get('/api/v1/reports', {
        dashboard_id: dashboardId,
        limit: 50,
      })
      setVersions(resp.items || [])
    } catch {
      setVersions([])
    } finally {
      setHistoryLoading(false)
    }
  }

  const openHistory = () => {
    setHistoryOpen(true)
    loadVersions()
  }

  // 查看历史版本
  const viewVersion = (rid: string) => {
    setHistoryOpen(false)
    if (rid === reportId) return
    setLoading(true)
    navigate(`/report?report_id=${rid}&dashboard_id=${dashboardId}`)
  }

  // 下载HTML
  const handleDownload = () => {
    if (!htmlContent) return
    const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${reportData?.title || '报告'}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (error) {
    return (
      <div className="report-page">
        <Alert type="error" message={error} showIcon />
        <Button onClick={() => navigate(-1)} style={{ marginTop: 16 }}>返回</Button>
      </div>
    )
  }

  return (
    <div className="report-page">
      {/* 顶部导航 */}
      <div className="report-header">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
        <h1 style={{ flex: 1, textAlign: 'center', margin: 0 }}>
          {reportData?.title || '分析报告'}
        </h1>
        <div style={{ display: 'flex', gap: 8 }}>
          {dashboardId && (
            <Tooltip title="回看该看板的历史报告版本">
              <Button icon={<HistoryOutlined />} onClick={openHistory}>
                历史版本
              </Button>
            </Tooltip>
          )}
          <Button icon={<ReloadOutlined />} onClick={handleGenerate} loading={loading}>
            重新生成
          </Button>
          <Button type="primary" icon={<DownloadOutlined />} onClick={handleDownload} disabled={!htmlContent}>
            下载HTML
          </Button>
        </div>
      </div>

      {/* LLM状态提示 */}
      {reportData && (
        <Alert
          type={reportData.llm_used ? 'success' : 'warning'}
          message={reportData.llm_used ? 'AI解读已启用' : 'AI解读不可用，以下为确定性摘要（基于真实数据聚合）'}
          showIcon
          style={{ margin: '12px 0' }}
        />
      )}

      {/* 报告内容 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
          <p style={{ color: '#999', marginTop: 16 }}>正在生成报告，请稍候...</p>
        </div>
      ) : htmlContent ? (
        <div className="report-iframe-container">
          <iframe
            srcDoc={htmlContent}
            title="report"
            className="report-iframe"
            sandbox="allow-same-origin"
          />
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <p style={{ color: '#999' }}>暂无报告，点击上方「重新生成」</p>
          {!dashboardId && (
            <Button type="primary" onClick={handleGenerate}>
              从当前看板生成报告
            </Button>
          )}
        </div>
      )}

      {/* 历史版本抽屉 */}
      <Drawer
        title="历史版本"
        placement="right"
        width={380}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      >
        {historyLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin />
            <p style={{ color: '#999', marginTop: 12 }}>加载历史版本...</p>
          </div>
        ) : versions.length === 0 ? (
          <Empty description="暂无历史版本" />
        ) : (
          <div className="version-list">
            {versions.map((v) => (
              <div
                key={v.report_id}
                className={`version-item ${v.report_id === reportId ? 'version-item-active' : ''}`}
                onClick={() => viewVersion(v.report_id)}
              >
                <div className="version-item-title">
                  {v.title || '未命名报告'}
                  {v.report_id === reportId && <Tag color="blue" style={{ marginLeft: 8 }}>当前</Tag>}
                </div>
                <div className="version-item-meta">
                  <Tooltip title={v.version_id}>
                    <span>版本 {v.version_id.slice(0, 8)}</span>
                  </Tooltip>
                  <span>图表 {v.chart_count}</span>
                  <span>{v.llm_used ? 'AI解读' : '确定性摘要'}</span>
                </div>
                <div className="version-item-time">{v.generated_at}</div>
              </div>
            ))}
          </div>
        )}
      </Drawer>
    </div>
  )
}
