import { useState, useRef, useCallback, useEffect } from 'react'
import { Card, Upload, Button, Progress, message, Modal, Typography, Space, List, Tag, Table, Steps, Segmented, Spin } from 'antd'
import { InboxOutlined, PlusOutlined, FileExcelOutlined, CloseCircleOutlined, CloseOutlined, ReloadOutlined, DownloadOutlined, FileTextOutlined, ExclamationCircleOutlined, CheckCircleOutlined, WarningOutlined, FolderOpenOutlined, SafetyOutlined, ThunderboltOutlined, ShareAltOutlined, ArrowRightOutlined, DownOutlined, UpOutlined } from '@ant-design/icons'
import type { UploadFile, UploadProps } from 'antd/es/upload/interface'
import './UploadPage.css'
import { SheetSelectModal, EncodingSelectModal } from '../../components/modals'
import QualityCheckPanel, { type QualityCheckStatus } from '../../components/quality/QualityCheckPanel'
import LoadingPage from '../../components/charts/LoadingPage'
import { useNavigate } from 'react-router-dom'
import { authHeaders } from '../../utils/request'

const { Dragger } = Upload
const { Title, Text } = Typography

// 首页信息区：四步流程
const HOME_STEPS = [
  { no: 1, title: '上传资料', desc: 'Excel / Word / PDF / 图片 / CSV / JSON 自动解析，多文件一次搞定' },
  { no: 2, title: '数据治理', desc: '识别数据根与逻辑错误，推荐清洗方案，须确认后执行' },
  { no: 3, title: '智能分析', desc: 'AI 聚焦分析维度，可信数据沉淀每一个指标' },
  { no: 4, title: '生成报告', desc: '输出带图表与数据血缘的专业报告，可迭代、可分享、可导出' },
]

// 首页信息区：核心能力
const HOME_CAPS = [
  { icon: <FileTextOutlined />, title: '多格式解析', desc: '表格、文档、扫描件、图片一次上传，结构化抽取' },
  { icon: <SafetyOutlined />, title: '数据治理', desc: '12 类质量问题自动扫描，脏数据无所遁形' },
  { icon: <ThunderboltOutlined />, title: '专业洞察', desc: '洞察分析新视角，不只描述现象，给出可执行建议' },
  { icon: <ShareAltOutlined />, title: '分享导出', desc: '专注分析掌握线索，PDF / Word / Excel 一键导出' },
]

// 上传状态类型
interface UploadItem {
  uid: string
  name: string
  size: number
  status: 'uploading' | 'done' | 'error' | 'removed'
  progress: number
  fileId?: string
  hash?: string
  errorCode?: string
  errorMessage?: string
}

// API配置
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 看板生成完成的全局墓碑标记（fid -> dashboardId），独立于会话存储：
// 即使 genMap 因"重新生成"等操作被清掉，恢复会话时也不会把已生成看板的文件再塞回上传队列
const GEN_DONE_KEY = 'upload_gen_done_map'
function readGenDoneMap(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(GEN_DONE_KEY) || '{}') } catch { return {} }
}
function markGenDone(fid: string, dashboardId: string) {
  try {
    localStorage.setItem(GEN_DONE_KEY, JSON.stringify({ ...readGenDoneMap(), [fid]: dashboardId }))
  } catch { /* localStorage 满时静默忽略 */ }
}

// 用户主动「取消生成看板」的标记（fid -> true）。
// 语义（方案 C）：上传 + 质检已完成 → 数据集是稳定资产；「生成看板」是独立可选动作。
// 取消只结束"生成"这一个动作，数据集保留、不再当作"未完成任务"反复提示。
const GEN_CANCELED_KEY = 'upload_gen_canceled_map'
function readGenCanceledMap(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(GEN_CANCELED_KEY) || '{}') } catch { return {} }
}
function markGenCanceled(fid: string) {
  try {
    localStorage.setItem(GEN_CANCELED_KEY, JSON.stringify({ ...readGenCanceledMap(), [fid]: true }))
  } catch { /* localStorage 满时静默忽略 */ }
}

export default function UploadPage() {
  const [fileList, setFileList] = useState<UploadItem[]>([])
  const [uploading, setUploading] = useState(false)
  // 3.1：上传≥1份后 Dragger 收缩为一行摘要（不占第一屏），点"继续上传"再展开
  const [uploadExpanded, setUploadExpanded] = useState(false)
  // 3.1 深度补充：上传队列同样会撑满首屏（N 份文件 = N 行），全部完成后一并收缩
  const [queueExpanded, setQueueExpanded] = useState(false)
  const [duplicateModal, setDuplicateModal] = useState<{
    visible: boolean
    file: UploadItem | null
  }>({ visible: false, file: null })
  const [errorModal, setErrorModal] = useState<{
    visible: boolean
    code: string
    message: string
    fileName: string
  }>({ visible: false, code: '', message: '', fileName: '' })
  
  // M1-06: Sheet选择和编码选择弹窗
  const [sheetModal, setSheetModal] = useState<{
    visible: boolean
    fileId: string
    fileName: string
    sheets: any[]
  }>({ visible: false, fileId: '', fileName: '', sheets: [] })
  
  const [encodingModal, setEncodingModal] = useState<{
    visible: boolean
    fileId: string
    fileName: string
    detectedEncoding: string
    confidence: number
    needsSelection: boolean
    previewData?: any
  }>({ visible: false, fileId: '', fileName: '', detectedEncoding: '', confidence: 0, needsSelection: false })
  
  const [previewMap, setPreviewMap] = useState<Record<string, { data: any; fileName: string }>>({})
  const [activeFileId, setActiveFileId] = useState<string | null>(null)
  // 预览失败的文件记录，用于显示重试按钮
  const [previewFailures, setPreviewFailures] = useState<Record<string, string>>({})
  // 数据集映射：fileId → datasetId（用于质检API调用）
  const [datasetMap, setDatasetMap] = useState<Record<string, string>>({})
  const [creatingDataset, setCreatingDataset] = useState<Record<string, boolean>>({})
  // 数据集创建失败记录
  const [datasetErrors, setDatasetErrors] = useState<Record<string, { message: string; timeout: boolean }>>({})
  // 各文件质检状态（用于Tab标记和全局摘要）
  const [qcStatusMap, setQcStatusMap] = useState<Record<string, QualityCheckStatus>>({})

  // 各文件看板生成完成标记（持久化，返回本页时不再显示"待生成看板"）
  const [genMap, setGenMap] = useState<Record<string, { done: boolean; dashboardId: string }>>({})

  // AI出图加载页
  const [loadingModalOpen, setLoadingModalOpen] = useState(false)
  const [loadingComplete, setLoadingComplete] = useState(false)
  const navigate = useNavigate()

  // 拖拽态管理：控制 Dragger 高亮边框，避免原生拖拽幽灵镜像残留
  const [dragging, setDragging] = useState(false)
  
  const abortControllers = useRef<Map<string, AbortController>>(new Map())
  // 存储原始File对象用于重试上传
  const fileRefs = useRef<Map<string, File>>(new Map())

  // ====== 问题5：会话持久化（异常退出恢复） ======
  const SESSION_KEY = 'upload_session'
  const [abandonModalOpen, setAbandonModalOpen] = useState(false)
  const [sessionRestored, setSessionRestored] = useState(false)
  // 从会话恢复出来的文件（非本次新上传）：其质检结果已在后端落地，
  // 恢复时直接读取，不自动重跑一次质检（方案 B）
  const [restoredFileIds, setRestoredFileIds] = useState<Record<string, boolean>>({})
  // 一次性守卫：防止 effect 重复触发导致恢复流程并发执行、toast 弹两次
  const restoreStartedRef = useRef(false)
  // 任务结束标记：任一文件看板生成完成即视为"本次上传任务结束"，
  // 整个会话作废——重新进入上传页应为干净初始态（历史看板在"历史分析项目"入口）
  const taskFinishedRef = useRef(false)

  // 保存会话到 localStorage
  const saveSession = () => {
    // 任务已结束（看板已生成）后不再回写会话，避免作废的会话被重新保存
    if (taskFinishedRef.current) return
    try {
      const session = {
        fileList: fileList.filter(f => f.status === 'done'),
        previewMap: Object.fromEntries(
          Object.entries(previewMap).map(([k, v]) => [k, { data: v.data, fileName: v.fileName }])
        ),
        datasetMap,
        previewFailures: Object.fromEntries(Object.entries(previewFailures)),
        datasetErrors: Object.fromEntries(Object.entries(datasetErrors)),
        genMap,
        activeFileId: activeFileId || (Object.keys(previewMap)[0] || null),
      }
      localStorage.setItem(SESSION_KEY, JSON.stringify(session))
    } catch (e) {
      // localStorage 可能满，静默忽略
    }
  }

  // 恢复会话
  // 规则：已生成看板的文件视为"本上传任务已结束"，不再恢复到上传页。
  // 用户可去对应看板内迭代；重新进入上传页应从干净的空状态开始（可上传新数据、生成新看板）。
  // 判定优先级：后端查询（数据集是否已有看板）> 本地墓碑 > 会话 genMap。
  const restoreSession = async () => {
    if (restoreStartedRef.current) return
    restoreStartedRef.current = true
    try {
      const raw = localStorage.getItem(SESSION_KEY)
      if (!raw) return
      const session = JSON.parse(raw)
      if (!session.fileList || session.fileList.length === 0) {
        localStorage.removeItem(SESSION_KEY)
        return
      }
      const gen = session.genMap || {}
      // 墓碑标记一并纳入：凡是已生成过看板的文件，一律不恢复到上传队列
      const doneTombstones = readGenDoneMap()
      const completedIds = new Set<string>([
        ...Object.keys(gen).filter(k => gen[k]?.done),
        ...Object.keys(doneTombstones),
      ])

      // ★ 后端兜底（2026-09-18）：墓碑只在本浏览器且 onComplete 触发过才有值。
      // 修复上线前保存的旧会话、或换浏览器打开时墓碑缺失，已生成看板的文件
      // 会重新回到上传队列。数据集是否已有看板以后端为准：逐数据集查询，
      // 命中则补写墓碑并视为已完成。
      const sessionDatasetMap: Record<string, string> = session.datasetMap || {}
      const dsIds = Array.from(new Set(Object.values(sessionDatasetMap).filter(Boolean)))
      if (dsIds.length > 0) {
        const dashByDs = new Map<string, string>()
        await Promise.all(dsIds.map(async dsId => {
          try {
            // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 /dashboards/by-dataset/*，已带 authHeaders()
            const res = await fetch(`${API_BASE}/dashboards/by-dataset/${dsId}`, { headers: authHeaders() })
            if (!res.ok) return
            const data = await res.json()
            const first = (data?.items || [])[0]
            if (first?.id) dashByDs.set(dsId, first.id)
          } catch { /* 后端不可用时不阻塞恢复流程，仅退回本地判定 */ }
        }))
        Object.entries(sessionDatasetMap).forEach(([fid, dsId]) => {
          const dashId = dashByDs.get(dsId as string)
          if (dashId && !completedIds.has(fid)) {
            completedIds.add(fid)
            markGenDone(fid, dashId) // 补写墓碑，后续恢复不再依赖后端查询
          }
        })
        // 已有看板的数据集清理遗留的生成进度 run_id，避免自动重开生成弹窗
        dashByDs.forEach((_dashId, dsId) => {
          localStorage.removeItem(`brain_run_${dsId}`)
        })
      }

      // 过滤掉已完成看板的文件及其关联数据
      const nextFileList = session.fileList.filter((f: UploadItem) => !(f.fileId && completedIds.has(f.fileId)))
      const nextPreviewMap = { ...(session.previewMap || {}) }
      const nextDatasetMap = { ...(session.datasetMap || {}) }
      const nextPreviewFailures = { ...(session.previewFailures || {}) }
      const nextDatasetErrors = { ...(session.datasetErrors || {}) }
      const nextGenMap = { ...gen }
      completedIds.forEach(id => {
        delete nextPreviewMap[id]
        delete nextDatasetMap[id]
        delete nextPreviewFailures[id]
        delete nextDatasetErrors[id]
        delete nextGenMap[id]
      })
      // 墓碑标记保留（不删），防止后续操作再次把已完成文件带回队列

      // 所有文件都已生成看板 → 全部结束，返回干净的初始空状态
      if (nextFileList.length === 0) {
        localStorage.removeItem(SESSION_KEY)
        return
      }

      setFileList(nextFileList)
      setPreviewMap(nextPreviewMap)
      setDatasetMap(nextDatasetMap)
      setPreviewFailures(nextPreviewFailures)
      setDatasetErrors(nextDatasetErrors)
      setGenMap(nextGenMap)
      if (session.activeFileId && nextPreviewMap[session.activeFileId]) {
        setActiveFileId(session.activeFileId)
      } else {
        setActiveFileId(Object.keys(nextPreviewMap)[0] || null)
      }
      setSessionRestored(true)

      // 标记为"从会话恢复而来"：质检面板据此直接读后端已存结果，不自动重跑（方案 B）
      const restoredIds: Record<string, boolean> = {}
      nextFileList.forEach((f: UploadItem) => { if (f.fileId) restoredIds[f.fileId] = true })
      setRestoredFileIds(restoredIds)

      // 恢复提示（方案 A + C）：
      // 已建数据集 = 上传+质检已完成，是"可继续生成看板"的稳定资产 → 静默恢复，不弹 toast；
      // 只有尚未建数据集（真的只传了一半）才提示"未完成的上传任务"。
      const hasReadyAsset = nextFileList.some((f: UploadItem) => !!f.fileId && !!nextDatasetMap[f.fileId])
      if (!hasReadyAsset) {
        message.info('检测到未完成的上传任务，已恢复其中未生成看板的部分')
      }
    } catch (e) {
      localStorage.removeItem(SESSION_KEY)
    }
  }

  // 删除某个已上传文件（报表 tab 上的 × 按钮）
  // 从本次任务移除该文件的全部状态；若已创建数据集则顺带请求后端删除；已生成的看板不受影响
  const handleDeleteFile = (fid: string) => {
    const fileName = previewMap[fid]?.fileName || fid
    Modal.confirm({
      title: `删除报表「${fileName}」？`,
      content: '将从本次任务中移除该文件及其质检记录；已生成的看板不受影响。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const dsId = datasetMap[fid]
        // 中断进行中的上传
        abortControllers.current.get(fid)?.abort()
        abortControllers.current.delete(fid)
        fileRefs.current.delete(fid)
        setFileList(prev => prev.filter(f => f.fileId !== fid))
        setPreviewMap(prev => { const n = { ...prev }; delete n[fid]; return n })
        setQcStatusMap(prev => { const n = { ...prev }; delete n[fid]; return n })
        setDatasetMap(prev => { const n = { ...prev }; delete n[fid]; return n })
        setPreviewFailures(prev => { const n = { ...prev }; delete n[fid]; return n })
        setDatasetErrors(prev => { const n = { ...prev }; delete n[fid]; return n })
        setGenMap(prev => { const n = { ...prev }; delete n[fid]; return n })
        // 若删的是当前激活 tab，切到剩余第一个
        if (activeFileId === fid) {
          const rest = Object.keys(previewMap).filter(k => k !== fid)
          setActiveFileId(rest[0] || null)
        }
        message.success(`已删除「${fileName}」`)
        // 后端数据集异步删除（失败不影响前端移除）
        if (dsId) {
          // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 DELETE /datasets/{id}，已带 authHeaders()
          fetch(`${API_BASE}/datasets/${dsId}`, { method: 'DELETE', headers: authHeaders() }).catch(() => {})
        }
      },
    })
  }

  // 放弃会话 — 清除所有状态并二次确认后回到初始
  const handleAbandon = () => {
    localStorage.removeItem(SESSION_KEY)
    setFileList([])
    setPreviewMap({})
    setDatasetMap({})
    setPreviewFailures({})
    setGenMap({})
    setActiveFileId(null)
    setSessionRestored(false)
    setAbandonModalOpen(false)
    message.success('已放弃当前进度')
  }

  // 挂载时恢复会话
  useEffect(() => {
    restoreSession()
  }, [])

  // 状态变化时自动保存会话（仅在有已上传文件时）
  useEffect(() => {
    if (fileList.some(f => f.status === 'done') || Object.keys(previewMap).length > 0) {
      saveSession()
    }
  }, [fileList, previewMap, datasetMap, previewFailures, activeFileId, genMap])

  // 恢复会话后：若该数据集存在未结束的后台生成任务(run_id)，自动重新打开生成弹窗
  // 解决"提交生成看板后离开页面，回来弹窗消失、进度丢失、需重新开始"的问题
  const autoRestoredDsRef = useRef<string>('')
  useEffect(() => {
    if (!sessionRestored) return
    // 等待 activeFileId 与 datasetMap 就绪后再判定
    const fid = activeFileId || Object.keys(datasetMap)[0]
    const dsId = fid ? datasetMap[fid] : ''
    if (!dsId) return
    if (autoRestoredDsRef.current === dsId) return
    // 该文件看板已生成完成，无需再自动重开弹窗
    if (fid && genMap[fid]?.done) return
    const storedRunId = localStorage.getItem(`brain_run_${dsId}`)
    if (storedRunId) {
      // 任务已完成且已查看过看板时，run_id 会被清除；存在即表示还有可恢复的进度/结果
      autoRestoredDsRef.current = dsId
      setLoadingModalOpen(true)
    }
  }, [sessionRestored, activeFileId, datasetMap])

  // ====== 结束问题5 ======

  // 检查文件是否已存在（通过hash或文件名）
  const checkDuplicate = (file: File): Promise<boolean> => {
    // 简化版：检查同名文件
    const existing = fileList.find(item => item.name === file.name && item.status === 'done')
    return Promise.resolve(!!existing)
  }

  // M1-06: 检查是否需要Sheet选择或多编码
  const checkFileNeedsSelection = async (fileId: string, fileName: string, fileExt: string) => {
    try {
      // 获取预览信息
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 GET /files/{id}/preview，已带 authHeaders()
      const response = await fetch(`${API_BASE}/files/${fileId}/preview`, { headers: authHeaders() })
      
      // 先检查响应Content-Type是否为JSON，避免非JSON响应导致解析失败
      const contentType = response.headers.get('content-type') || ''
      if (!contentType.includes('application/json') && !contentType.includes('application/problem+json')) {
        const text = await response.text()
        throw new Error(`服务器返回异常: ${text.substring(0, 100)}`)
      }
      
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail?.message || `HTTP ${response.status}`)
      }

      // ★ 先存储预览数据，这样不管后续走哪个分支（弹窗/直接展示），预览都在 tab 里
      setPreviewMap(prev => ({ ...prev, [fileId]: { data: data.preview, fileName } }))
      setActiveFileId(fileId)
      
      // Excel多Sheet处理
      if (data.type === 'excel' && data.sheets && data.sheets.length > 1) {
        setSheetModal({
          visible: true,
          fileId,
          fileName,
          sheets: data.sheets
        })
        return false // 等待用户选择
      }
      
      // CSV编码选择
      if (data.type === 'csv' && data.needs_encoding_selection) {
        setEncodingModal({
          visible: true,
          fileId,
          fileName,
          detectedEncoding: data.detected_encoding,
          confidence: data.encoding_confidence,
          needsSelection: data.needs_encoding_selection,
          previewData: data.preview
        })
        return false // 等待用户选择
      }
      
      return true // 预览成功，可以继续
      
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : '未知错误'
      message.error(`获取文件预览失败: ${errMsg}`)
      // 预览失败时，也加入previewMap占位，让文件tab能显示出来
      setPreviewMap(prev => ({ ...prev, [fileId]: { data: { error: true, errorMessage: errMsg, columns: [], rows: [], total_rows: 0, total_cols: 0 }, fileName } }))
      setActiveFileId(fileId)
      setPreviewFailures(prev => ({ ...prev, [fileId]: fileName }))
      return false // 返回false，不创建数据集
    }
  }

  // 重试预览
  const retryPreview = async (fileId: string) => {
    const fileName = previewFailures[fileId] || fileId
    const fileExt = fileName.substring(fileName.lastIndexOf('.')).toLowerCase()
    // 清除失败记录，重新尝试
    setPreviewFailures(prev => {
      const next = { ...prev }
      delete next[fileId]
      return next
    })
    await checkFileNeedsSelection(fileId, fileName, fileExt)
  }

  // 创建数据集（用于质检API）
  const createDataset = async (fileId: string, fileName: string, sheetName?: string, encoding?: string) => {
    setCreatingDataset(prev => ({ ...prev, [fileId]: true }))
    // 清除之前的错误
    setDatasetErrors(prev => {
      const next = { ...prev }
      delete next[fileId]
      return next
    })
    
    // 30秒超时
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 30000)
    
    try {
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 POST /datasets，已带 authHeaders()
      const response = await fetch(`${API_BASE}/datasets`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          file_id: fileId,
          name: fileName.replace(/\.(xlsx|xls|csv)$/i, ''),
          sheet_name: sheetName,
          encoding,
        }),
        signal: controller.signal
      })
      clearTimeout(timeoutId)
      
      const data = await response.json()
      if (response.ok) {
        setDatasetMap(prev => ({ ...prev, [fileId]: data.dataset_id }))
        message.success('数据集创建成功')
        return data.dataset_id
      } else {
        const errMsg = data.detail?.message || '创建数据集失败'
        message.error(errMsg)
        setDatasetErrors(prev => ({ ...prev, [fileId]: { message: errMsg, timeout: false } }))
        return null
      }
    } catch (error: any) {
      clearTimeout(timeoutId)
      if (error.name === 'AbortError') {
        const errMsg = '数据集创建超时（30秒），请检查文件大小或重试'
        message.error(errMsg)
        setDatasetErrors(prev => ({ ...prev, [fileId]: { message: errMsg, timeout: true } }))
      } else {
        const errMsg = '创建数据集网络错误'
        message.error(errMsg)
        setDatasetErrors(prev => ({ ...prev, [fileId]: { message: errMsg, timeout: false } }))
      }
      return null
    } finally {
      setCreatingDataset(prev => ({ ...prev, [fileId]: false }))
    }
  }

  // 选择Sheet后
  const handleSheetConfirm = async (sheetName: string) => {
    const { fileId, fileName } = sheetModal
    setSheetModal(prev => ({ ...prev, visible: false }))
    
    try {
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 select-sheet，已带 authHeaders()
      const response = await fetch(`${API_BASE}/files/${fileId}/select-sheet`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ file_id: fileId, sheet_name: sheetName })
      })
      
      const data = await response.json()
      
      if (response.ok) {
        setPreviewMap(prev => ({ ...prev, [fileId]: { data: data.preview, fileName } }))
        setActiveFileId(fileId)
        message.success(`已选择工作表: ${sheetName}`)
        // 创建数据集
        await createDataset(fileId, fileName, sheetName)
      } else {
        message.error(data.detail?.message || '选择失败')
      }
    } catch (error) {
      message.error('网络错误')
    }
  }

  // 选择编码后
  const handleEncodingConfirm = async (encoding: string) => {
    const { fileId, fileName } = encodingModal
    setEncodingModal(prev => ({ ...prev, visible: false }))
    
    try {
      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 select-encoding，已带 authHeaders()
      const response = await fetch(`${API_BASE}/files/${fileId}/select-encoding`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ file_id: fileId, encoding })
      })
      
      const data = await response.json()
      
      if (response.ok) {
        setPreviewMap(prev => ({ ...prev, [fileId]: { data: data.preview, fileName } }))
        setActiveFileId(fileId)
        message.success(`已使用编码: ${encoding}`)
        // 创建数据集
        await createDataset(fileId, fileName, undefined, encoding)
      } else {
        message.error(data.detail?.message || '编码选择失败')
      }
    } catch (error) {
      message.error('网络错误')
    }
  }

  // 上传文件
  const uploadFile = async (file: File, uid: string) => {
    const controller = new AbortController()
    abortControllers.current.set(uid, controller)

    const formData = new FormData()
    formData.append('file', file)

    try {
      setFileList(prev => prev.map(item => 
        item.uid === uid ? { ...item, status: 'uploading', progress: 0 } : item
      ))

      // eslint-disable-next-line no-restricted-globals -- 强制鉴权端点 POST /files（FormData 上传），已带 authHeaders() 且不设 Content-Type 以保留 multipart boundary
      const response = await fetch(`${API_BASE}/files`, {
        method: 'POST',
        headers: authHeaders(),
        body: formData,
        signal: controller.signal,
      })

      // 防御性解析：后端重启/代理中断时会返回空 body，直接 res.json() 会抛
      // "Unexpected end of JSON input" 这种误导性错误。先读 text 再安全解析，
      // 解析失败时按"服务不可用"给出人话提示。
      const rawText = await response.text()
      let data: any = null
      try {
        data = rawText ? JSON.parse(rawText) : null
      } catch {
        data = null
      }

      if (!response.ok || !data) {
        if (response.ok && !data) {
          // HTTP 200 但 body 不是合法 JSON → 后端正在重启/被代理截断
          const svcMsg = '服务响应异常（后端可能正在重启），请稍等几秒后重试'
          setFileList(prev => prev.map(item =>
            item.uid === uid ? { ...item, status: 'error', errorCode: 'SERVICE_UNSTABLE', errorMessage: svcMsg } : item
          ))
          message.error(svcMsg)
          return
        }
        // 处理错误
        const errorCode = data?.detail?.code || `UPLOAD_${response.status}`
        const errorMessage = data?.detail?.message || `上传失败（HTTP ${response.status}）`

        setFileList(prev => prev.map(item => 
          item.uid === uid ? { 
            ...item, 
            status: 'error',
            errorCode,
            errorMessage
          } : item
        ))

        // 显示错误弹窗
        if (errorCode === 'UPLOAD_413' || errorCode === 'UPLOAD_415') {
          setErrorModal({
            visible: true,
            code: errorCode,
            message: errorMessage,
            fileName: file.name
          })
        } else {
          message.error(errorMessage)
        }
        return
      }

      // 上传成功
      setFileList(prev => prev.map(item => 
        item.uid === uid ? { 
          ...item, 
          status: 'done',
          progress: 100,
          fileId: data.file_id,
          hash: data.hash
        } : item
      ))

      message.success(`${file.name} 上传成功`)
      // 3.1：上传完成后自动收缩 Dragger，让首屏让位给内容（可点"继续上传"再展开）
      setUploadExpanded(false)

      // M1-06: 检查是否需要Sheet选择或编码选择
      const fileExt = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
      const needsSelection = await checkFileNeedsSelection(data.file_id, file.name, fileExt)
      // 如果不需要选择（直达预览），且预览成功，再创建数据集
      if (needsSelection) {
        await createDataset(data.file_id, file.name)
      }

    } catch (error) {
      const err = error as any
      if (err?.name === 'AbortError') {
        // 用户取消
        setFileList(prev => prev.filter(item => item.uid !== uid))
      } else {
        // 判定是否为网络/后端不可用，避免把"服务器挂了"误报成"文件格式不对"
        const rawMsg = String(err?.message || '')
        const isNetwork =
          err instanceof TypeError ||
          /failed to fetch|networkerror|network error|fetch failed|connect/i.test(rawMsg) ||
          rawMsg.includes('network')
        const code = isNetwork ? 'NETWORK_ERROR' : 'UPLOAD_FAIL'
        const msg = isNetwork
          ? '无法连接服务器，请检查后端服务是否已启动后重试'
          : (rawMsg && !/failed to fetch/i.test(rawMsg)
              ? rawMsg
              : '文件解析失败，请确认文件内容为规范表格数据后重试')

        setFileList(prev => prev.map(item => 
          item.uid === uid ? { 
            ...item, 
            status: 'error',
            errorCode: code,
            errorMessage: msg
          } : item
        ))
        
        // 错误弹窗（区分网络错误与文件错误）
        setErrorModal({
          visible: true,
          code,
          message: msg,
          fileName: file.name
        })
      }
    } finally {
      abortControllers.current.delete(uid)
    }
  }

  // 自定义上传处理
  const customRequest: UploadProps['customRequest'] = async ({ file, onProgress, onSuccess, onError }) => {
    const fileObj = file as File
    const uid = (fileObj as any).uid || Date.now().toString()

    // 保存原始File引用用于重试
    fileRefs.current.set(uid, fileObj)

    // 检查文件大小 (139MB触发413)
    if (fileObj.size > 100 * 1024 * 1024) {
      setErrorModal({
        visible: true,
        code: 'UPLOAD_413',
        message: `文件过大: ${(fileObj.size / 1024 / 1024).toFixed(1)}MB > 100MB`,
        fileName: fileObj.name
      })
      onError?.(new Error('File too large'))
      return
    }

    // 检查重复文件
    const isDuplicate = await checkDuplicate(fileObj)
    if (isDuplicate) {
      const newItem: UploadItem = {
        uid,
        name: fileObj.name,
        size: fileObj.size,
        status: 'uploading',
        progress: 0
      }
      setFileList(prev => [...prev, newItem])
      setDuplicateModal({ visible: true, file: newItem })
      return
    }

    // 添加到列表并开始上传
    const newItem: UploadItem = {
      uid,
      name: fileObj.name,
      size: fileObj.size,
      status: 'uploading',
      progress: 0
    }
    setFileList(prev => [...prev, newItem])

    await uploadFile(fileObj, uid)
  }

  // 取消上传
  const handleCancel = (uid: string) => {
    const controller = abortControllers.current.get(uid)
    if (controller) {
      controller.abort()
    }
    // 清理该文件的预览数据
    const item = fileList.find(f => f.uid === uid)
    if (item?.fileId) {
      setPreviewMap(prev => {
        const next = { ...prev }
        delete next[item.fileId!]
        return next
      })
      setPreviewFailures(prev => {
        const next = { ...prev }
        delete next[item.fileId!]
        return next
      })
      setActiveFileId(prev => prev === item.fileId ? null : prev)
    }
    setFileList(prev => prev.filter(item => item.uid !== uid))
  }

  // 重试上传
  const handleRetry = (item: UploadItem) => {
    const originalFile = fileRefs.current.get(item.uid)
    if (!originalFile) {
      message.error('文件已失效，请重新选择文件上传')
      return
    }
    // 重置状态
    setFileList(prev => prev.map(f => 
      f.uid === item.uid ? { ...f, status: 'uploading', progress: 0, errorCode: undefined, errorMessage: undefined } : f
    ))
    uploadFile(originalFile, item.uid)
  }

  // 重复文件三选操作
  const handleDuplicateAction = (action: 'overwrite' | 'save' | 'cancel') => {
    if (!duplicateModal.file) return

    const { file } = duplicateModal

    if (action === 'cancel') {
      // 清理该文件的预览数据
      if (file.fileId) {
        setPreviewMap(prev => {
          const next = { ...prev }
          delete next[file.fileId!]
          return next
        })
        setActiveFileId(prev => prev === file.fileId ? null : prev)
      }
      setFileList(prev => prev.filter(item => item.uid !== file.uid))
    } else if (action === 'overwrite') {
      // 覆盖：删除旧文件预览数据，等待重新上传
      if (file.fileId) {
        setPreviewMap(prev => {
          const next = { ...prev }
          delete next[file.fileId!]
          return next
        })
        setActiveFileId(prev => prev === file.fileId ? null : prev)
      }
      message.info('覆盖上传...')
      // TODO: 调用删除API后重新上传
    } else if (action === 'save') {
      // 另存：修改文件名后上传
      message.info('另存为新文件...')
      // TODO: 添加后缀后重新上传
    }

    setDuplicateModal({ visible: false, file: null })
  }

  // 下载模板
  const downloadTemplate = () => {
    // 创建示例CSV模板
    const template = '日期,客户编号,贷款金额,担保类型\n2024-01-01,C001,100000,信用\n2024-01-02,C002,200000,抵押'
    const blob = new Blob([template], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '数据上传模板.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  // 上传配置
  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.xlsx,.xls,.csv,.json,.tsv,.docx,.pdf,.md,.txt,.png,.jpg,.jpeg,.webp',
    customRequest,
    showUploadList: false,
    beforeUpload: (file) => {
      const validExts = ['.xlsx', '.xls', '.csv', '.json', '.tsv', '.docx', '.pdf', '.md', '.txt', '.png', '.jpg', '.jpeg', '.webp']
      const isValidType = validExts.some(ext => file.name.toLowerCase().endsWith(ext))
      
      if (!isValidType) {
        setErrorModal({
          visible: true,
          code: 'UPLOAD_415',
          message: `不支持的文件类型，仅支持 .xlsx, .xls, .csv, .json, .tsv, .docx, .pdf, .md, .txt, .png, .jpg, .jpeg, .webp`,
          fileName: file.name
        })
        return Upload.LIST_IGNORE
      }
      return true
    }
  }

  const activePreview = activeFileId ? previewMap[activeFileId] : null
  const doneFiles = fileList.filter(f => f.status === 'done')
  const previewFileIds = Object.keys(previewMap)
  // 3.1：已上传≥1份 → 收缩 Dragger（用 done 份数，避免"上传中"就误收缩）
  const shouldCollapse = doneFiles.length > 0 && !uploadExpanded

  // 3.1 深度补充：上传队列是 N 行列表，N 大时同样撑满首屏 → 全部结束后一并收缩成一行。
  // 边界：只要还有 uploading / error 项就必须保持展开（用户要看进度条与重试按钮）。
  const activeQueueItems = fileList.filter(
    f => f.status === 'uploading' || f.status === 'error'
  )
  const queueCollapsed =
    fileList.length > 0 && activeQueueItems.length === 0 && !queueExpanded

  return (
    <div className="upload-page">
      {/* Hero 首屏标语区 */}
      <div className="home-hero">
        <div className="home-hero-pill">✦ 上传资料，一句话生成专业分析报告</div>
        <h1 className="home-hero-title">把杂乱数据，变成能直接汇报的分析报告</h1>
        <p className="home-hero-sub">
          上传 Excel、Word、PDF、图片或 CSV，自动完成数据治理与分析，
          输出资深数据分析师水准的报告，全程可追溯、可迭代
        </p>
      </div>

      <Steps
        size="small"
        direction="horizontal"
        responsive={false}
        current={activeFileId && genMap[activeFileId]?.done ? 3 : activePreview ? 2 : doneFiles.length > 0 ? 1 : 0}
        style={{ marginTop: 16, marginBottom: 8 }}
        items={[
          { title: '上传文件' },
          { title: '预览确认' },
          { title: '质检修复' },
          { title: '生成看板' },
        ]}
      />

      <Card className="upload-card" style={{ marginTop: 16 }}>
        {shouldCollapse ? (
          // 3.1：已上传≥1份 → 收缩为一行摘要，不再占第一屏
          <div className="upload-collapsed-bar">
            <span className="upload-collapsed-text">
              已上传 {doneFiles.length} 份，可继续上传
            </span>
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => setUploadExpanded(true)}
            >
              继续上传
            </Button>
          </div>
        ) : (
          // 边界：已上传≥1份却手动展开了 → 提供"收起"回到收缩态（否则只能靠下次上传成功才收缩）
          doneFiles.length > 0 && (
            <div className="upload-collapsed-bar" style={{ marginBottom: 12 }}>
              <span className="upload-collapsed-text">
                已上传 {doneFiles.length} 份，正在追加上传
              </span>
              <Button
                type="link"
                size="small"
                onClick={() => setUploadExpanded(false)}
              >
                收起
              </Button>
            </div>
          )
        )}
        {!shouldCollapse && (
          <div
            style={{ borderRadius: 8 }}
            onDragEnter={(e) => { e.preventDefault(); setDragging(true) }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={(e) => { e.preventDefault(); setDragging(false) }}
            onDrop={(e) => { e.preventDefault(); setDragging(false) }}
          >
            <Dragger
              {...uploadProps}
              className="upload-dragger"
              style={dragging ? { borderColor: '#1677ff', background: '#e6f4ff' } : undefined}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="upload-text">拖拽文件到这里，或点击上传</p>
              <p className="ant-upload-hint">
                支持 Excel、Word、PDF、图片、CSV、JSON，单个文件最大 100MB
              </p>
              <Button type="primary" icon={<FolderOpenOutlined />} style={{ marginTop: 16 }} tabIndex={-1}>
                选择文件开始分析
              </Button>
            </Dragger>
          </div>
        )}
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Button type="link" icon={<DownloadOutlined />} onClick={downloadTemplate}>
            下载参考模板
          </Button>
        </div>
      </Card>

      {/* 上传列表：全部结束后收缩为一行，避免 N 份文件撑满首屏（3.1 深度补充） */}
      {fileList.length > 0 && queueCollapsed && (
        <div className="upload-collapsed-bar" style={{ marginTop: 24 }}>
          <span className="upload-collapsed-text">
            上传队列 · {fileList.length} 份文件，全部完成
          </span>
          <Button
            type="link"
            size="small"
            icon={<DownOutlined />}
            onClick={() => setQueueExpanded(true)}
          >
            展开队列
          </Button>
        </div>
      )}
      {fileList.length > 0 && !queueCollapsed && (
        <Card
          title="上传队列"
          className="upload-list-card"
          style={{ marginTop: 24 }}
          extra={
            activeQueueItems.length === 0 ? (
              <Button
                type="link"
                size="small"
                icon={<UpOutlined />}
                onClick={() => setQueueExpanded(false)}
              >
                收起
              </Button>
            ) : null
          }
        >
          <List
            dataSource={fileList}
            renderItem={item => (
              <List.Item
                actions={[
                  item.status === 'uploading' && (
                    <Button 
                      type="text" 
                      icon={<CloseCircleOutlined />}
                      onClick={() => handleCancel(item.uid)}
                    >
                      取消
                    </Button>
                  ),
                  item.status === 'error' && (
                    <Button 
                      type="text" 
                      icon={<ReloadOutlined />}
                      onClick={() => handleRetry(item)}
                    >
                      重试
                    </Button>
                  )
                ].filter(Boolean)}
              >
                <List.Item.Meta
                  avatar={<FileExcelOutlined style={{ fontSize: 24, color: '#52c41a' }} />}
                  title={
                    <Space>
                      {item.name}
                      {item.status === 'done' && <Tag color="success">完成</Tag>}
                      {item.status === 'error' && <Tag color="error">失败</Tag>}
                    </Space>
                  }
                  description={
                    <div style={{ width: 300 }}>
                      {item.status === 'uploading' && (
                        <Progress 
                          percent={item.progress} 
                          size="small" 
                          status="active"
                        />
                      )}
                      {item.status === 'error' && (
                        <Text type="danger" style={{ fontSize: 12 }}>
                          {item.errorMessage}
                        </Text>
                      )}
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {(item.size / 1024).toFixed(1)} KB
                        {item.hash && ` • Hash: ${item.hash.substring(0, 8)}...`}
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* 重复文件弹窗 - 三选 */}
      <Modal
        title="文件已存在"
        open={duplicateModal.visible}
        onCancel={() => handleDuplicateAction('cancel')}
        footer={[
          <Button key="cancel" onClick={() => handleDuplicateAction('cancel')}>
            取消
          </Button>,
          <Button key="save" onClick={() => handleDuplicateAction('save')}>
            另存为新文件
          </Button>,
          <Button key="overwrite" type="primary" danger onClick={() => handleDuplicateAction('overwrite')}>
            覆盖原文件
          </Button>
        ]}
      >
        <p>检测到同名文件已存在：</p>
        <p><strong>{duplicateModal.file?.name}</strong></p>
        <p>请选择操作方式：</p>
        <ul>
          <li><strong>覆盖原文件</strong>：删除旧文件，使用新文件</li>
          <li><strong>另存为新文件</strong>：保留旧文件，新文件重命名保存</li>
          <li><strong>取消</strong>：放弃本次上传</li>
        </ul>
      </Modal>

      {/* 错误弹窗 */}
      <Modal
        title={errorModal.code === 'UPLOAD_413' ? '文件过大' : 
               errorModal.code === 'UPLOAD_415' ? '格式不支持' : '上传失败'}
        open={errorModal.visible}
        onCancel={() => setErrorModal({ ...errorModal, visible: false })}
        footer={[
          <Button key="template" type="primary" onClick={downloadTemplate}>
            下载模板
          </Button>,
          <Button key="ok" onClick={() => setErrorModal({ ...errorModal, visible: false })}>
            知道了
          </Button>
        ]}
      >
        <div className="error-modal-content">
          <p><strong>文件名：</strong>{errorModal.fileName}</p>
          <p><strong>错误信息：</strong></p>
          <div className="error-message-box">
            {errorModal.code === 'UPLOAD_413' && (
              <>
                <Tag color="error">UPLOAD_413</Tag>
                <p>文件超过 100MB 限制</p>
                <p>{errorModal.message}</p>
              </>
            )}
            {errorModal.code === 'UPLOAD_415' && (
              <>
                <Tag color="error">UPLOAD_415</Tag>
                <p>不支持的文件格式</p>
                <p>{errorModal.message}</p>
                <p style={{ marginTop: 8 }}>支持的格式：<Tag>.xlsx</Tag> <Tag>.xls</Tag> <Tag>.csv</Tag> <Tag>.json</Tag> <Tag>.tsv</Tag> <Tag>.docx</Tag> <Tag>.pdf</Tag> <Tag>.md</Tag> <Tag>.txt</Tag> <Tag>.png</Tag> <Tag>.jpg</Tag> <Tag>.webp</Tag></p>
              </>
            )}
            {errorModal.code === 'UPLOAD_FAIL' && (
              <>
                <Tag color="error">UPLOAD_FAIL</Tag>
                <p>文件无法识别</p>
                <p>{errorModal.message}</p>
              </>
            )}
            {errorModal.code === 'NETWORK_ERROR' && (
              <>
                <Tag color="error">NETWORK_ERROR</Tag>
                <p>上传失败：无法连接服务器</p>
                <p>{errorModal.message}</p>
              </>
            )}
          </div>
          {errorModal.code !== 'NETWORK_ERROR' && (
            <p style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
              💡 提示：请按照标准模板格式上传数据
            </p>
          )}
        </div>
      </Modal>

      {/* M1-06: Sheet选择弹窗 */}
      <SheetSelectModal
        visible={sheetModal.visible}
        fileId={sheetModal.fileId}
        fileName={sheetModal.fileName}
        sheets={sheetModal.sheets}
        onCancel={() => setSheetModal(prev => ({ ...prev, visible: false }))}
        onConfirm={handleSheetConfirm}
      />

      {/* M1-06: 编码选择弹窗 */}
      <EncodingSelectModal
        visible={encodingModal.visible}
        fileId={encodingModal.fileId}
        fileName={encodingModal.fileName}
        detectedEncoding={encodingModal.detectedEncoding}
        confidence={encodingModal.confidence}
        needsSelection={encodingModal.needsSelection}
        previewData={encodingModal.previewData}
        onCancel={() => setEncodingModal(prev => ({ ...prev, visible: false }))}
        onConfirm={handleEncodingConfirm}
      />

      {/* 每个文件一个统一的处理卡片：预览+质检+生成看板 */}
      {previewFileIds.length > 0 && (
        <>
          {/* 文件切换标签页 + 各文件质检状态标记 */}
          <Card className="file-tabs-card" style={{ marginTop: 24 }}>
            <Segmented
              value={activeFileId || previewFileIds[0]}
              onChange={(key) => setActiveFileId(key as string)}
              options={previewFileIds.map(fid => {
                const st = qcStatusMap[fid]
                let statusBadge = null
                if (st?.checked) {
                  if (st.hasBlocking) {
                    statusBadge = <Tag color="error" style={{ marginLeft: 4, fontSize: 11 }}>阻断</Tag>
                  } else if (st.totalIssues > 0) {
                    statusBadge = <Tag color="warning" style={{ marginLeft: 4, fontSize: 11 }}>提示</Tag>
                  } else {
                    statusBadge = <Tag color="success" style={{ marginLeft: 4, fontSize: 11 }}>通过</Tag>
                  }
                } else if (datasetMap[fid]) {
                  statusBadge = <Tag color="processing" style={{ marginLeft: 4, fontSize: 11 }}>质检中</Tag>
                }
                return {
                  value: fid,
                  label: (
                    <Space size={4}>
                      <FileTextOutlined />
                      <span>{previewMap[fid].fileName}</span>
                      {statusBadge}
                    </Space>
                  )
                }
              })}
            />
            {/* 全局质检状态摘要 */}
            {previewFileIds.length > 1 && (
              <div style={{ marginTop: 12, padding: '8px 12px', background: '#fafafa', borderRadius: 6, fontSize: 13 }}>
                {(() => {
                  const checkedFiles = previewFileIds.filter(fid => qcStatusMap[fid]?.checked)
                  const blockingFiles = checkedFiles.filter(fid => qcStatusMap[fid]?.hasBlocking)
                  const passFiles = checkedFiles.filter(fid => !qcStatusMap[fid]?.hasBlocking && qcStatusMap[fid]?.totalIssues === 0)
                  const warnFiles = checkedFiles.filter(fid => !qcStatusMap[fid]?.hasBlocking && qcStatusMap[fid]!.totalIssues > 0)
                  const pendingFiles = previewFileIds.filter(fid => !qcStatusMap[fid]?.checked)
                  
                  return (
                    <Space size={16} wrap>
                      <span>共 {previewFileIds.length} 个报表</span>
                      {passFiles.length > 0 && <span style={{ color: '#52c41a' }}><CheckCircleOutlined /> {passFiles.length} 通过</span>}
                      {warnFiles.length > 0 && <span style={{ color: '#faad14' }}><WarningOutlined /> {warnFiles.length} 有提示</span>}
                      {blockingFiles.length > 0 && <span style={{ color: '#ff4d4f' }}><CloseCircleOutlined /> {blockingFiles.length} 有阻断</span>}
                      {pendingFiles.length > 0 && <span style={{ color: '#8c8c8c' }}>待质检 {pendingFiles.length}</span>}
                      {blockingFiles.length > 0 && (
                        <span style={{ color: '#ff4d4f', fontWeight: 500 }}>
                          需修复阻断项：{blockingFiles.map(fid => previewMap[fid]?.fileName || fid).join('、')}
                        </span>
                      )}
                    </Space>
                  )
                })()}
              </div>
            )}
          </Card>

          {/* 预览失败文件 — 显示重试按钮 */}
          {Object.keys(previewFailures).length > 0 && (
            <Card size="small" style={{ marginTop: 12, background: '#fff2f0', border: '1px solid #ffccc7' }}>
              <Space>
                <span style={{ color: '#cf1322' }}>部分文件预览失败：</span>
                {Object.entries(previewFailures).map(([fid, fname]) => (
                  <Button key={fid} size="small" type="link" onClick={() => retryPreview(fid)}>
                    重试 {fname}
                  </Button>
                ))}
              </Space>
            </Card>
          )}

          {/* 当前文件统一处理卡片：预览 → 质检 → 生成看板 */}
          {activeFileId && activePreview && (
            <Card
              className="file-processing-card"
              style={{ marginTop: 16, border: '1px solid #d9d9d9' }}
              title={
                <Space>
                  <FileExcelOutlined style={{ fontSize: 18, color: '#1677ff' }} />
                  <span style={{ fontWeight: 600, fontSize: 15 }}>
                    报表：{activePreview.fileName}
                  </span>
                  {(() => {
                    const st = qcStatusMap[activeFileId]
                    if (st?.checked) {
                      if (st.hasBlocking) return <Tag color="error" icon={<CloseCircleOutlined />}>有阻断项</Tag>
                      if (st.totalIssues > 0) return <Tag color="warning" icon={<WarningOutlined />}>有提示</Tag>
                      return <Tag color="success" icon={<CheckCircleOutlined />}>质检通过</Tag>
                    }
                    if (datasetMap[activeFileId]) return <Tag color="processing">质检中</Tag>
                    return <Tag color="blue">数据处理中</Tag>
                  })()}
                  {datasetMap[activeFileId] && !qcStatusMap[activeFileId]?.checked && (
                    <Tag color="green">数据集已就绪</Tag>
                  )}
                  {genMap[activeFileId]?.done && (
                    <Tag color="success" icon={<CheckCircleOutlined />}>看板已生成</Tag>
                  )}
                </Space>
              }
              extra={
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Step 2: 预览确认 → Step 3: 质检修复 → Step 4: 生成看板
                  </Text>
                </Space>
              }
            >
              {/* 1. 数据预览 */}
              <div className="file-section">
                <div className="file-section-header">
                  <Text strong style={{ fontSize: 14 }}>
                    <CheckCircleOutlined style={{ color: '#1677ff', marginRight: 6 }} />
                    数据预览
                  </Text>
                  {activePreview.data.error ? (
                    <Tag color="red">预览失败</Tag>
                  ) : (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {activePreview.data.total_rows?.toLocaleString() || 0} 行 × {activePreview.data.total_cols || 0} 列
                      {activePreview.data.total_rows > 5 && '（仅预览前5行）'}
                    </Text>
                  )}
                </div>
                
                {activePreview.data.error ? (
                  <div style={{ textAlign: 'center', padding: '24px 0' }}>
                    <CloseCircleOutlined style={{ fontSize: 36, color: '#ff4d4f' }} />
                    <p style={{ marginTop: 8, color: '#ff4d4f' }}>{activePreview.data.errorMessage}</p>
                    <Button 
                      type="primary" 
                      icon={<ReloadOutlined />} 
                      onClick={() => retryPreview(activeFileId!)}
                      style={{ marginTop: 8 }}
                    >
                      重新加载预览
                    </Button>
                  </div>
                ) : (
                  <div className="file-preview-table">
                    <Table
                      dataSource={activePreview.data.rows.map((row: any[], idx: number) => ({
                        key: idx,
                        ...activePreview.data.columns.reduce((acc: any, col: string, i: number) => {
                          acc[col] = row[i]
                          return acc
                        }, {} as any)
                      }))}
                      columns={activePreview.data.columns.map((col: string) => ({
                        title: col,
                        dataIndex: col,
                        ellipsis: true
                      }))}
                      pagination={false}
                      size="small"
                      scroll={{ x: 'max-content' }}
                      style={{ marginTop: 8 }}
                    />
                  </div>
                )}
              </div>

                {
                (genMap[activeFileId]?.done) ? (
                  <div className="file-section" style={{ textAlign: 'center', padding: '32px 0' }}>
                    <CheckCircleOutlined style={{ fontSize: 44, color: '#52c41a' }} />
                    <h3 style={{ margin: '12px 0 4px', fontWeight: 600, fontSize: 18 }}>看板已生成</h3>
                    <Text type="secondary">该报表已完成看板生成，可直接查看或重新生成</Text>
                    <div style={{ marginTop: 18 }}>
                      <Space>
                        {genMap[activeFileId]?.dashboardId && (
                          <Button
                            type="primary"
                            icon={<FileTextOutlined />}
                            onClick={() => { window.location.href = `/dashboard?id=${genMap[activeFileId].dashboardId}` }}
                          >
                            查看看板
                          </Button>
                        )}
                        <Button
                          icon={<ReloadOutlined />}
                          onClick={() => setGenMap(prev => { const n = { ...prev }; delete n[activeFileId!]; return n })}
                        >
                          重新生成看板
                        </Button>
                      </Space>
                    </div>
                  </div>
                ) : (activeFileId && datasetMap[activeFileId]) ? (
                  <QualityCheckPanel
                    fileId={activeFileId}
                    fileName={previewMap[activeFileId]?.fileName}
                    datasetId={datasetMap[activeFileId]}
                    autoCheck={!restoredFileIds[activeFileId]}
                    onProceed={() => setLoadingModalOpen(true)}
                    onStatusChange={(status) => {
                      setQcStatusMap(prev => ({ ...prev, [activeFileId]: status }))
                    }}
                  />
                ) : creatingDataset[activeFileId] ? (
                  <div style={{ textAlign: 'center', padding: '32px 0' }}>
                    <Spin size="large" />
                    <p style={{ marginTop: 16, color: '#8c8c8c' }}>正在创建数据集，请稍候...</p>
                    <p style={{ color: '#8c8c8c', fontSize: 12 }}>大数据文件可能需要较长时间（最大等待30秒）</p>
                  </div>
                ) : datasetErrors[activeFileId] ? (
                  <div style={{ textAlign: 'center', padding: '32px 0', background: '#fff2f0', borderRadius: 8 }}>
                    <CloseCircleOutlined style={{ fontSize: 36, color: '#ff4d4f' }} />
                    <p style={{ marginTop: 16, color: '#ff4d4f', fontWeight: 500 }}>
                      {datasetErrors[activeFileId].message}
                    </p>
                    <Button
                      type="primary"
                      icon={<ReloadOutlined />}
                      onClick={async () => {
                        const fileName = previewMap[activeFileId]?.fileName || activeFileId;
                        if (previewMap[activeFileId]?.data?.sheet_name) {
                          await createDataset(activeFileId, fileName, previewMap[activeFileId].data.sheet_name);
                        } else {
                          await createDataset(activeFileId, fileName);
                        }
                      }}
                      style={{ marginTop: 12 }}
                    >
                      重新尝试
                    </Button>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: '24px 0', color: '#8c8c8c' }}>
                    <Text type="secondary">预览完成后正在准备数据，即将开始质检...</Text>
                  </div>
                )
              }
            </Card>
          )}
        </>
      )}

      {/* ====== 首页信息区（数据上传下方） ====== */}
      <div className="home-section">
        <h2 className="home-section-title">四步完成一份分析报告</h2>
        <p className="home-section-sub">从原始资料到可交付报告的完整链路，每一步都可查看与干预</p>
        <div className="home-steps-grid">
          {HOME_STEPS.map((s, i) => (
            <div key={s.no} className="home-step-item">
              <div className="home-step-card">
                <div className="home-step-no">{s.no}</div>
                <div className="home-step-title">{s.title}</div>
                <div className="home-step-desc">{s.desc}</div>
              </div>
              {i < HOME_STEPS.length - 1 && <div className="home-step-arrow">→</div>}
            </div>
          ))}
        </div>
      </div>

      <div className="home-section">
        <h2 className="home-section-title">核心能力</h2>
        <p className="home-section-sub">面向办公人员与财务场景设计，不需要懂 SQL，也不需要懂统计</p>
        <div className="home-caps-grid">
          {HOME_CAPS.map(c => (
            <div key={c.title} className="home-cap-card">
              <div className="home-cap-icon">{c.icon}</div>
              <div className="home-cap-title">{c.title}</div>
              <div className="home-cap-desc">{c.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="home-history">
        <Button type="link" onClick={() => navigate('/dashboards')}>
          查看历史分析项目 <ArrowRightOutlined />
        </Button>
      </div>

      {/* 问题5：放弃缓冲按钮 — 底部通栏 */}
      {(fileList.some(f => f.status === 'done') || Object.keys(previewMap).length > 0) && (
        <div style={{ marginTop: 32, textAlign: 'center', borderTop: '1px solid var(--border-color, #e8e8e8)', paddingTop: 24 }}>
          <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
            已有文件上传和质检记录，下次打开页面可继续加工
          </Text>
          <Button
            danger
            icon={<CloseCircleOutlined />}
            onClick={() => setAbandonModalOpen(true)}
          >
            放弃缓冲，重新开始
          </Button>
        </div>
      )}

      {/* 问题5：放弃二次确认弹窗 */}
      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#faad14' }} />
            确认放弃当前进度？
          </Space>
        }
        open={abandonModalOpen}
        onCancel={() => setAbandonModalOpen(false)}
        okText="确认放弃"
        cancelText="继续加工"
        okButtonProps={{ danger: true }}
        onOk={handleAbandon}
      >
        <div style={{ padding: '8px 0' }}>
          <p>放弃后，当前上传的文件和质检记录将被清除。</p>
          <p>如需重新上传数据生成新看板，请确认放弃。</p>
          <Text type="warning" style={{ fontSize: 12 }}>
            此操作不可撤销，但之前已保存到数据库的文件仍可通过其他方式访问。
          </Text>
        </div>
      </Modal>

      {/* AI生成看板加载页 - Modal弹窗形式，不遮挡页面 */}
      <Modal
        open={loadingModalOpen}
        onCancel={() => {
          // 方案 C：取消只结束"生成看板"这一个动作，上传+质检产物保留、会话不作废
          const cancelFid = activeFileId || Object.keys(datasetMap)[0] || ''
          if (cancelFid) markGenCanceled(cancelFid)
          setLoadingModalOpen(false)
          setLoadingComplete(false)
        }}
        footer={null}
        centered
        width={Math.min(720, (typeof window !== 'undefined' ? window.innerWidth : 720) - 48)}
        closable
        maskClosable={false}
        keyboard={false}
        destroyOnClose
        styles={{
          body: { padding: '24px 24px', maxHeight: 'calc(100vh - 140px)', overflowY: 'auto' },
        }}
      >
        <LoadingPage
          datasetId={datasetMap[activeFileId || ''] || ''}
          datasetName={activeFileId ? (previewMap[activeFileId]?.fileName || '数据集') : '数据集'}
          onCancel={() => {
            // 方案 C：同上——LoadingPage 内已调后端 /cancel 并清 brain_run_{dsId}，
            // 这里再打"已取消生成"标记，恢复时按"可继续"处理，不再当未完成任务告警
            const cancelFid = activeFileId || Object.keys(datasetMap)[0] || ''
            if (cancelFid) markGenCanceled(cancelFid)
            setLoadingModalOpen(false)
            setLoadingComplete(false)
          }}
          onComplete={(dashboardId: string) => {
            setLoadingComplete(true)
            setLoadingModalOpen(false)
            // 记录该文件看板已生成（持久化），返回本页时显示"已生成看板"而非"待生成看板"
            const doneFid = activeFileId || Object.keys(datasetMap)[0] || ''
            const doneDsId = datasetMap[doneFid] || ''
            if (doneFid) {
              setGenMap(prev => ({ ...prev, [doneFid]: { done: true, dashboardId: dashboardId || '' } }))
              // 全局墓碑：之后无论会话状态如何变化，该文件都不会再回到上传队列
              markGenDone(doneFid, dashboardId || '')
            }
            if (doneDsId) {
              localStorage.removeItem(`brain_run_${doneDsId}`)
            }
            // ★ 看板生成成功 = 本次上传任务结束：整个会话作废。
            // 重新进入上传页应为干净初始态，不再把"未生成看板"的旧文件搬回队列
            //（历史看板通过"查看历史分析项目"进入迭代）
            taskFinishedRef.current = true
            localStorage.removeItem(SESSION_KEY)
            const targetId = dashboardId && dashboardId.startsWith('dash_') ? dashboardId : ''
            setTimeout(() => {
              if (targetId) {
                window.location.href = `/dashboard?id=${targetId}`
              } else {
                // 生成未返回有效看板ID：留在列表也提示（用 message）
                message.info('看板已生成，但未返回有效看板ID，已跳转到看板列表')
                window.location.href = '/dashboard'
              }
            }, 500)
          }}
        />
      </Modal>
    </div>
  )
}
