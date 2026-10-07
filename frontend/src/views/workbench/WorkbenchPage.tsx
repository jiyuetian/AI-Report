import React from 'react'
import { Card, Button, Alert } from 'antd'
import { useNavigate } from 'react-router-dom'
import { UploadOutlined, BarChartOutlined, FileTextOutlined, ArrowRightOutlined } from '@ant-design/icons'
import './WorkbenchPage.css'

interface BoardThumb {
  title: string
  tag: string
  meta: string
  bars: Array<number>
  bg: string
}

const recentBoards: BoardThumb[] = [
  { title: '渠道贷款风险监控看板', tag: '风控', meta: '2小时前更新', bg: 'linear-gradient(160deg,#1677ff22,#722ed111)', bars: [40, 70, 55, 85] },
  { title: '月度资金流入流出分析', tag: '财务', meta: '昨天更新', bg: 'linear-gradient(160deg,#13c2c222,#1677ff11)', bars: [60, 35, 80, 50] },
  { title: '多头借贷客户分布', tag: '风控', meta: '3天前更新', bg: 'linear-gradient(160deg,#faad1422,#ff4d4f11)', bars: [45, 75, 30, 60] },
  { title: '各业务线回款进度', tag: '财务', meta: '上周更新', bg: 'linear-gradient(160deg,#52c41a22,#13c2c211)', bars: [65, 50, 90, 40] },
]

export default function WorkbenchPage() {
  const nav = useNavigate()
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const name = user.full_name || user.username || '你'
  const h = new Date().getHours()
  const greet = h < 6 ? '凌晨好' : h < 9 ? '早上好' : h < 12 ? '上午好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'

  return (
    <div className="wb">
      <div className="wb-hero">
        <div>
          <h2 className="wb-hello">{greet}，{name} 👋</h2>
          <p className="wb-hello-sub">上传一份数据，3 分钟内获得你的第一张 AI 看板。</p>
        </div>
        <Button type="primary" size="large" icon={<UploadOutlined />} className="wb-hero-btn" onClick={() => nav('/upload')}>
          ＋ 上传数据，开始分析
        </Button>
      </div>

      <div className="wb-entry-grid">
        <Card className="wb-entry hoverable" onClick={() => nav('/dashboards')}>
          <div className="wb-entry-ico">🗂️</div>
          <div className="wb-entry-name">我的看板</div>
          <div className="wb-entry-desc">12 份看板 · 最近更新 2 小时前</div>
        </Card>
        <Card className="wb-entry hoverable" onClick={() => nav('/dashboard')}>
          <div className="wb-entry-ico">📊</div>
          <div className="wb-entry-name">智能看板演示</div>
          <div className="wb-entry-desc">查看与对话面板联动的智能看板</div>
        </Card>
        <Card className="wb-entry hoverable" onClick={() => nav('/upload')}>
          <div className="wb-entry-ico">📖</div>
          <div className="wb-entry-name">新手引导</div>
          <div className="wb-entry-desc">3 步上手：上传数据 → AI 分析 → 生成看板</div>
        </Card>
      </div>

      <Card className="wb-recent">
        <div className="wb-recent-head">
          <span className="wb-recent-title">最近看板</span>
          <a className="wb-recent-all" onClick={() => nav('/dashboards')}>查看全部 →</a>
        </div>
        <div className="wb-recent-grid">
          {recentBoards.map((b, i) => (
            <Card key={i} className="wb-board hoverable" onClick={() => nav('/dashboard')}>
              <div className="wb-board-thumb" style={{ background: b.bg }}>
                {b.bars.map((hgt, j) => (
                  <i key={j} style={{ height: `${hgt}%`, background: `rgba(22,119,255,${0.5 + j * 0.16})` }} />
                ))}
              </div>
              <div className="wb-board-name">{b.title}</div>
              <div className="wb-board-meta">{b.tag} · {b.meta}</div>
            </Card>
          ))}
        </div>
      </Card>

      <Alert
        className="wb-notice"
        type="info"
        showIcon
        message={<span><b>系统公告：</b>8月15日 22:00-24:00 系统升级维护，期间 AI 分析服务暂停，已生成看板可正常查看。</span>}
      />
    </div>
  )
}