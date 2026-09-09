import { ConfigProvider, theme as antdTheme } from 'antd'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import MainLayout from './components/layout/MainLayout'
import LoginPage from './views/login/LoginPage'
import ForbiddenPage from './views/error/ForbiddenPage'

// 对齐原型 index.html 的 AntD5 设计令牌
const RISK_THEME_TOKENS = {
  colorPrimary: '#1677ff',
  colorPrimaryHover: '#4096ff',
  colorSuccess: '#52c41a',
  colorWarning: '#faad14',
  colorError: '#ff4d4f',
  colorInfo: '#1677ff',
  borderRadius: 8,
  fontSize: 14,
}

// React Query客户端
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
})

function ProtectedRoute({ children, requireAdmin = false }: { children: React.ReactNode, requireAdmin?: boolean }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  if (requireAdmin) {
    const user = JSON.parse(localStorage.getItem('user') || '{}')
    const isAdmin = user.roles?.includes('admin')
    if (!isAdmin) return <Navigate to="/403" replace />
  }
  // 兜底：外层全宽容器，让 AntD Layout 的 flex 子元素能正确计算宽度，
  // 避免在窄视口/响应模式下 Sider+Content 塌成 0 宽的细竖条。
  // 注意：使用 '100%' 而非 '100vw'，避免 Windows 滚动条导致水平溢出。
  return <div style={{ width: '100%', minHeight: '100vh', overflowX: 'hidden' }}>{children}</div>
}

import UploadPage from './views/upload/UploadPage'
import WorkbenchPage from './views/workbench/WorkbenchPage'
import DashboardPage from './views/dashboard/DashboardPage'
import DashboardListPage from './views/dashboard/DashboardListPage'
import LineagePage from './views/lineage/LineagePage'
import SharePage from './views/share/SharePage'
import AdminPage from './views/admin/AdminPage'
import ReportPage from './views/report/ReportPage'
import { Card, Button } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'

// 演示占位屏：用于原型中仅作演示、还没落到独立 React 页的屏（多表/出图loading/异常集/状态演示等）
const DEMO_TITLES: Record<string, { title: string; desc: string; ico: string }> = {
  quality: { title: '数据预览与质检', desc: 'AI 已完成字段识别与六类质量校验（演示屏，可在「数据上传」流程中体验完整质检）', ico: '🔍' },
  multitable: { title: '多表接入与关联', desc: '多表关联能力研发中，敬请期待', ico: '🔗' },
  loading: { title: 'AI 出图 Loading', desc: '上传数据后全屏 AI 生成看板动画（演示）', ico: '✨' },
  fix: { title: '数据修复 / 异常全集', desc: '六类质量异常的处理与修复清单（演示）', ico: '🛡️' },
  ops: { title: '看板操作弹窗集', desc: '看板上的换图 / 新增 / 筛选 / 归因 / 改标题等操作弹窗集合（演示）', ico: '🧰' },
  fixresult: { title: '修复执行与二次质检', desc: '修复执行与二次质检门禁（演示）', ico: '🔧' },
  states: { title: '看板多状态演示', desc: '看板的加载 / 空 / 异常等多状态演示', ico: '🧩' },
  global: { title: '全局边界与兜底', desc: '接口异常 / 空结果 / 超时等全局兜底状态演示', ico: '🌐' },
}

function DemoPage() {
  const { key = 'states' } = useParams()
  const nav = useNavigate()
  const info = DEMO_TITLES[key] || DEMO_TITLES.states
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <Card style={{ width: 480, textAlign: 'center' }}>
        <div style={{ fontSize: 56, opacity: 0.6, marginBottom: 16 }}>{info.ico}</div>
        <h2 style={{ marginBottom: 8 }}>{info.title}</h2>
        <p style={{ color: '#999', marginBottom: 24 }}>{info.desc}</p>
        <Button type="primary" onClick={() => nav('/dashboard')}>返回看板</Button>
      </Card>
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        theme={{
          token: RISK_THEME_TOKENS as any,
          algorithm: antdTheme.defaultAlgorithm,
        }}
      >
        <BrowserRouter>
          <Routes>
            {/* 登录页 */}
            <Route path="/login" element={<LoginPage />} />
            {/* 403 */}
            <Route path="/403" element={<ForbiddenPage />} />

            {/* 主布局（需登录） */}
            <Route element={
              <ProtectedRoute>
                <MainLayout tokenCount={1250} tokenLimit={5000} />
              </ProtectedRoute>
            }>
              <Route path="/" element={<WorkbenchPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/dashboards" element={<DashboardListPage />} />
              <Route path="/lineage" element={<LineagePage />} />
              <Route path="/share" element={<SharePage />} />
              <Route path="/report" element={<ReportPage />} />
              {/* 原型演示占位屏 */}
              <Route path="/demo/:key" element={<DemoPage />} />
              <Route path="/admin" element={
                <ProtectedRoute requireAdmin>
                  <AdminPage />
                </ProtectedRoute>
              } />
            </Route>

            {/* 默认重定向 */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  )
}

export default App