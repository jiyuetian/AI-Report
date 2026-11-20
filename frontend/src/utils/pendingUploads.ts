/**
 * 会话失效后的待上传文件暂存（Task #721）
 *
 * 用浏览器原生 IndexedDB 直接存 File（structured clone 原生支持 Blob/File），不新增依赖。
 * 生命周期：上传前登记 → 401/失败时保留 → 重新登录回跳上传页 → 恢复队列自动重传
 *          → 成功后精确删除；用户取消/移除也精确删除。
 * 隐私模式或配额不足时静默降级为"仅本次内存可重试"，绝不阻断正常上传。
 */
const DB_NAME = 'ai_report_pending_uploads'
const STORE = 'pending'
const DB_VERSION = 1

export interface PendingUpload {
  uid: string
  name: string
  size: number
  type: string
  lastModified: number
  savedAt: number
  file: File
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB unavailable'))
      return
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'uid' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function savePendingUpload(rec: PendingUpload): Promise<void> {
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(rec)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch {
    /* 降级：IndexedDB 不可用时仍保留内存 File 引用，不影响本次上传 */
  }
}

export async function listPendingUploads(): Promise<PendingUpload[]> {
  try {
    const db = await openDb()
    const rows = await new Promise<PendingUpload[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).getAll()
      req.onsuccess = () => resolve((req.result || []) as PendingUpload[])
      req.onerror = () => reject(req.error)
    })
    db.close()
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}

export async function getPendingUpload(uid: string): Promise<PendingUpload | null> {
  try {
    const db = await openDb()
    const row = await new Promise<PendingUpload | undefined>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).get(uid)
      req.onsuccess = () => resolve(req.result as PendingUpload | undefined)
      req.onerror = () => reject(req.error)
    })
    db.close()
    return row && row.file ? row : null
  } catch {
    return null
  }
}

export async function deletePendingUpload(uid: string): Promise<void> {
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).delete(uid)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch {
    /* 忽略 */
  }
}
