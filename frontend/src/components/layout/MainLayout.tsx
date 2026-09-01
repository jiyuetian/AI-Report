import { useState } from 'react'
import { Layout, Menu, Button, Badge, Avatar, Dropdown, theme as antdTheme } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
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

const { Sider, Header, Content } = Layout

// 导航项（按 PRD 功能层级：一级页面入导航；异常弹窗/看板操作/分享导出/版本/对话历史均为页面内弹窗，不入导航）
interface NavChild { key: string; icon: React.ReactNode; label: string; path: string }
interface NavGroup { group: string; children: NavChild[] }

const navGroups: NavGroup[] = [
  {
    group: '工作台',
    children: [
      { key: '/', icon: <HomeOutlined />, label: '工作台 / 首页', path: '/' },
    ],
  },
  {
    group: '数据接入',
    children: [
      { key: '/upload', icon: <DatabaseOutlined />, label: '数据上传与加工', path: '/upload' },
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
  const [collapsed, setCollapsed] = useState(false)
  
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

  // 看板页/血缘从「我的看板」进入，归属到 /dashboards
  const activeKey =
    location.pathname.startsWith('/dashboard') || location.pathname.startsWith('/lineage')
      ? '/dashboards'
      : navGroups.flatMap(g => g.children).some(n => n.key === location.pathname)
        ? location.pathname
        : '/'

  // 生成分组菜单
  const menuItems = navGroups.map(g => ({
    type: 'group' as const,
    label: g.group,
    children: g.children.map(c => ({ key: c.key, icon: c.icon, label: c.label })),
  }))
  
  return (
    <Layout className="main-layout">
      {/* 侧边栏 */}
      <Sider 
        trigger={null} 
        collapsible 
        collapsed={collapsed}
        className="main-sider"
        width={236}
      >
        {/* Logo区域 */}
        <div className="sider-logo">
          <div className="logo-mark">AI</div>
          {!collapsed && (
            <div className="logo-text">
              <div className="logo-name">AI快速BI</div>
              <div className="logo-sub">报表工具</div>
            </div>
          )}
        </div>
        
        {/* 导航菜单 */}
        <Menu
          mode="inline"
          selectedKeys={[activeKey]}
          items={menuItems}
          onClick={({ key }) => handleNavClick(key)}
          className="main-menu"
        />
      </Sider>
      
      <Layout>
        {/* 顶部栏 */}
        <Header className="main-header">
          <div className="header-left">
            <Button 
              type="text"
              icon={collapsed ? <span className="collapse-icon">›</span> : <span className="collapse-icon">‹</span>}
              onClick={() => setCollapsed(!collapsed)}
              className="collapse-btn"
            />
          </div>
          
          <div className="header-right">
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
        
        {/* 内容区域 */}
        <Content className="main-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}