import { Layout, Menu, Button, Badge, Avatar, Dropdown } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useContext } from 'react'
import { AppThemeContext } from '../../themeContext'
import {
  HomeOutlined,
  DatabaseOutlined,
  SearchOutlined,
  LinkOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
  ApartmentOutlined,
  SafetyOutlined,
  ToolOutlined,
  FolderOpenOutlined,
 AppstoreOutlined,
  ExperimentOutlined,
  GlobalOutlined,
  SettingOutlined,
  MoonOutlined,
  SunOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined
} from '@ant-design/icons'
import './MainLayout.css'

const { Header, Content } = Layout

// 导航项（按 PRD 功能层级：一级页面入导航；异常弹窗/看板操作/分享导出/版本/对话历史均为页面内弹窗，不入导航）
interface NavChild { key: string; icon: React.ReactNode; label: string; path: string }
interface NavGroup { group: string; children: NavChild[] }

const navGroups: NavGroup[] = [
  {
    group: '数据接入',
    children: [
      { key: '/', icon: <DatabaseOutlined />, label: '数据上传', path: '/' },
    ],
  },
  {
    group: '我的看板',
    children: [
      { key: '/dashboards', icon: <FolderOpenOutlined />, label: '我的看板', path: '/dashboards' },
    ],
  },
  {
    group: '管理',
    children: [
      { key: '/admin', icon: <SettingOutlined />, label: '管理后台', path: '/admin' },
    ],
  },
]

interface MainLayoutProps {
  tokenCount?: number
  tokenLimit?: number
}

export default function MainLayout({ tokenCount = 0, tokenLimit = 5000 }: MainLayoutProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const appThemeCtx = useContext(AppThemeContext)

  // 计算Token使用率
  const tokenPercent = Math.min(100, (tokenCount / tokenLimit) * 100)
  const tokenStatus = tokenPercent > 90 ? 'error' : tokenPercent > 70 ? 'warning' : 'normal'
  
  // 用户菜单
  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人中心'
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '账号设置'
    },
    {
      type: 'divider' as const
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录'
    }
  ]
  
  const handleUserMenuClick = ({ key }: { key: string }) => {
    if (key === 'logout') {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      navigate('/login')
    } else if (key === 'profile') {
      navigate('/profile')
    }
  }
  
  const handleNavClick = (key: string) => {
    const all = navGroups.flatMap(g => g.children)
    const item = all.find(n => n.key === key)
    if (item) navigate(item.path)
  }

  // 看板页/血缘从「我的看板」进入，归属到 /dashboards；旧 /upload 链接归属到首页
  const activeKey =
    location.pathname.startsWith('/dashboard') || location.pathname.startsWith('/lineage')
      ? '/dashboards'
      : location.pathname.startsWith('/upload')
        ? '/'
        : navGroups.flatMap(g => g.children).some(n => n.key === location.pathname)
          ? location.pathname
          : '/'

  // 顶部水平菜单：把分组拍平成单层 items（横向菜单不展示分组标题）
  const menuItems = navGroups.flatMap(g => g.children).map(c => ({
    key: c.key,
    icon: c.icon,
    label: c.label,
  }))
  
  return (
    <Layout className="main-layout">
      {/* 顶部水平导航栏 */}
      <Header className="main-header top-nav">
        <div className="nav-left">
          {/* Logo */}
          <div className="sider-logo">
            <div className="logo-mark">AI</div>
            <div className="logo-text">
              <div className="logo-name">AI快速BI</div>
              <div className="logo-sub">报表工具</div>
            </div>
          </div>

          {/* 顶部水平菜单 */}
          <Menu
            mode="horizontal"
            selectedKeys={[activeKey]}
            items={menuItems}
            onClick={({ key }) => handleNavClick(key)}
            className="main-menu top-menu"
          />
        </div>

        <div className="header-right">
          {/* 主题切换：明/暗 */}
          <Button
            type="text"
            className="theme-toggle-btn"
            icon={appThemeCtx?.theme === 'dark' ? <SunOutlined /> : <MoonOutlined />}
            onClick={() => appThemeCtx?.toggle()}
            title={appThemeCtx?.theme === 'dark' ? '切换到明亮主题' : '切换到暗黑主题'}
          />

          {/* Token余量Chip — 紧凑模式 */}
          <div className={`token-chip ${tokenStatus}`}>
            <span className="token-icon">⚡</span>
            <span className="token-percent">{Math.round(tokenPercent)}%</span>
            {/* 悬停弹出详情 */}
            <div className="token-popover">
              <div className="token-popover-title">
                <span>今日额度</span>
                <span className="token-percent">{Math.round(tokenPercent)}%</span>
              </div>
              <div className="token-popover-numbers">
                <div className="token-popover-item">
                  <span className="value">{tokenCount.toLocaleString()}</span>
                  <span className="label">已用</span>
                </div>
                <div className="token-popover-item">
                  <span className="value">{tokenLimit.toLocaleString()}</span>
                  <span className="label">总额</span>
                </div>
                <div className="token-popover-item">
                  <span className="value">{(tokenLimit - tokenCount).toLocaleString()}</span>
                  <span className="label">剩余</span>
                </div>
              </div>
              <div className="token-popover-bar">
                <div className="token-popover-fill" style={{ width: `${tokenPercent}%` }} />
              </div>
              <div className="token-popover-note">
                {tokenStatus === 'error' ? '额度即将耗尽，请及时升级' : '每日额度按需分配'}
              </div>
            </div>
          </div>
          
          {/* 通知 */}
          <Badge count={5} size="small">
            <Button type="text" icon={<BellOutlined />} className="notify-btn" />
          </Badge>
          
          {/* 用户头像 */}
          <Dropdown 
            menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
            placement="bottomRight"
          >
            <Avatar 
              icon={<UserOutlined />}
              className="user-avatar"
              style={{ 
                background: 'linear-gradient(135deg, #13c2c2, #1677ff)',
                cursor: 'pointer'
              }}
            >
              U
            </Avatar>
          </Dropdown>
        </div>
      </Header>
      
      {/* 内容区域（顶部栏让位后，横向空间全部留给看板展示） */}
      <Content className="main-content">
        <Outlet />
      </Content>
    </Layout>
  )
}