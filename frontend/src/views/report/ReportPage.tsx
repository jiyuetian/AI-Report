"""
报告查看页 - 7章节图文报告展示
"""
import { useEffect, useState } from 'react'
import { Spin, Alert, Button } from 'antd'
import { ArrowLeftOutlined, DownloadOutlined, ReloadOutlined }
import { useNavigate, useSearchParams }
import axios from 'axios'
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

export default function ReportPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const reportId = searchParams.get('report_id')
  const dashboardId = searchParams.get('dashboard_id')

  const [loading, setLoading] = useState(true)
  const [reportData, setReportData] = useState<ReportData | null>(null)
  const [htmlContent, setHtmlContent] = useState<string>('')
  const [error, setError] = useState<string>('')

  // 生成报告
  const handleGenerate = async () => {
    if (!dashboardId) return
    setLoading(true)
    setError('')
    try {
      const resp = await axios.post('/api/v1/reports', {
        dashboard_id: dashboardId,
        force_regenerate: true,
      })
      const rid = resp.data.report_id
      window.location.href = `/report?report_id=${rid}&dashboard_id=${dashboardId}`
    } catch (e: any) {
      setError(e.response?.data?.detail || '报告生成失败')
    } finally {
      setLoading(false)
    }
  }

  // 加载报告
  useEffect(() => {
    if (!reportId) return
    ;(async () => {
      try {
        const [jsonResp, htmlResp] = await Promise.all([
          axios.get(`/api/v1/reports/${reportId}/json`),
          axios.get(`/api/v1/reports/${reportId}/html`),
        ])
        setReportData(jsonResp.data.data)
        setHtmlContent(htmlResp.data)
      } catch (e: any) {
        setError(e.response?.data?.detail || '报告加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [reportId])

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
    </div>
  )
}
