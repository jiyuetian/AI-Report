/**
 * SkillPanel —— Phase 5 前端收口薄壳。
 *
 * 设计原则（与后端 Skill 框架一致：薄封装、零视觉回归）：
 * - 仅在外层加一个「能力组件」来源条（展示当前面板由哪些后端 skill 驱动），
 *   满足设计文档「后端 skill → 前端入口自动出现」要求；
 * - 不重写任何暗色样式：容器沿用 theme.css 既有变量（data-theme=dark 下自动继承）；
 * - 面板业务内容（children）完全不变，避免破坏已对齐原型的布局。
 *
 * 用法：把现有面板的返回内容整体作为 children 传入即可。
 */
import React, { useEffect, useState } from 'react'
import { Tag, Tooltip } from 'antd'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface SkillMetaLite {
  id: string
  name: string
  description?: string
  tags?: string[]
  panel_kind?: string | null
}

interface SkillPanelProps {
  /** 只展示该 panel_kind 的 skill（与后端 SkillMeta.panel_kind 对应） */
  panelKind?: string
  /** 或按 tag 过滤 */
  tags?: string[]
  /** 来源条前缀文案（一般传面板标题） */
  title?: string
  children: React.ReactNode
  className?: string
}

export default function SkillPanel({ panelKind, tags, title, children, className }: SkillPanelProps) {
  const [skills, setSkills] = useState<SkillMetaLite[]>([])

  useEffect(() => {
    let alive = true
    const key = (tags || []).join(',')
    // eslint-disable-next-line no-restricted-globals -- 非强制鉴权端点 /skills，按设计不带 token
    fetch(`${API_BASE}/skills`)
      .then((r) => r.json())
      .then((d: { skills?: SkillMetaLite[] }) => {
        if (!alive) return
        const all = d.skills || []
        const filtered = all.filter(
          (s) =>
            (panelKind && s.panel_kind === panelKind) ||
            (tags && (s.tags || []).some((t) => tags.includes(t)))
        )
        setSkills(filtered)
      })
      .catch(() => {
        /* 接口不可用不影响面板渲染 */
      })
    return () => {
      alive = false
    }
  }, [panelKind, tags?.join(',')])

  return (
    <div className={`skill-panel${className ? ` ${className}` : ''}`}>
      {skills.length > 0 && (
        <div className="skill-panel__source">
          <span className="skill-panel__source-label">{title ? `${title} · ` : ''}能力组件：</span>
          {skills.map((s) => (
            <Tooltip key={s.id} title={s.description || s.id}>
              <Tag color="blue" bordered={false}>
                {s.name}
              </Tag>
            </Tooltip>
          ))}
        </div>
      )}
      {children}
    </div>
  )
}
