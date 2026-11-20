/**
 * 统一 API 请求封装
 * 自动注入 token(Authorization: Bearer)、解析错误、处理 JSON
 */
/**
 * API 基址唯一真相源（Task #713）：所有裸 fetch 组件一律从这里导入，禁止再各自定义
 * VITE_API_BASE_URL 或写死 /api/v1。可用 VITE_API_BASE_URL 覆盖，尾部斜杠统一去掉，
 * 避免 `${API_BASE}/path` 出现双斜杠 404。
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/**
 * Task #720：JWT 本地可用性检查。只解 payload 的 exp，不校验签名
 * （签名是否仍被服务端认可由后端 401 兜底判定，因为前端拿不到 SECRET_KEY）。
 * 修复前 ProtectedRoute 只判断 localStorage 里"有没有 token"，已过期/换密钥作废的
 * token 照样能进页面，直到上传时才炸一个看不懂的 HTTP 401。
 */
export function isTokenUsable(): boolean {
  const token = localStorage.getItem('token')
  if (!token) return false
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return false
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = decodeURIComponent(
      atob(b64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')
    )
    const exp = Number(JSON.parse(json)?.exp)
    if (!Number.isFinite(exp)) return false
    // 预留 30s 时钟偏移，避免"刚好到期"的边界抖动
    return exp * 1000 > Date.now() + 30_000
  } catch {
    return false
  }
}

/** 登录/注册类端点的 401 是"账号或密码错误"，不是会话失效，绝不能触发跳登录页。 */
function isAuthEndpoint(url: string): boolean {
  let path = url
  try { path = new URL(url, window.location.origin).pathname } catch { /* 相对路径直接判定 */ }
  return /\/auth\/(login|register|token|send-code|refresh|logout)(\/|$)/.test(path)
    || path.endsWith('/login')
}

// 同一次页面生命周期内只跳转一次，避免多个并发请求同时 401 导致重复 replace
let sessionExpiredHandled = false

/** 会话失效统一处理：清凭证 → 记回跳地址与提示 → 回登录页。 */
export function handleSessionExpired(): void {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  if (sessionExpiredHandled) return
  if (window.location.pathname.startsWith('/login')) return
  sessionExpiredHandled = true
  try { sessionStorage.setItem('auth_expired_notice', '1') } catch { /* 隐私模式忽略 */ }
  const redirect = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.replace(`/login?redirect=${redirect}`)
}

/** 统一解析后端 detail（可能是字符串，也可能是 {code,message}）为人话文案。 */
function detailText(d: any, fallback: string): string {
  if (d && typeof d === 'object') return String(d.message || d.code || fallback)
  return String(d || fallback)
}

/**
 * 给「裸 fetch」调用点用的鉴权头。
 * 背景：后端鉴权改造后 `POST /files`、`POST /datasets`、`POST /brain/run`、
 * `GET /files/{id}/preview`、`GET /brain/run/{id}/status` 等端点强制要求
 * `Authorization`，但部分组件直接用 fetch 绕过了 `request()` 封装 → 登录态下必 401。
 * 这些调用点必须带上这里返回的 headers。
 * 注意：只返回 Authorization，不设置 Content-Type —— 上传 FormData 时需要浏览器
 * 自动补 multipart boundary，手动设置会导致后端解析不到文件。
 */
export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra || {}) }
  const token = localStorage.getItem('token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}


/**
 * 给「非 SSE 的裸 fetch」统一补鉴权的薄封装。与 authHeaders() 不同，它直接发起请求并返回
 * 原始 Response，保留调用方对 res.ok / res.headers / res.body(ReadableStream) / signal 的
 * 完全控制。所有非流式裸 fetch 都应改走本函数，避免各组件重复拼 Authorization、并消除
 * `no-restricted-globals` 对裸 fetch 的限制（request.ts 是 fetch 唯一合法出处）。
 * SSE 流式调用（LoadingPage / ChatPanel）也走本函数取原始 Response 消费流，合理不走
 * request() 的 JSON 解析封装。
 */
export async function authorizedFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> | undefined) }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  // eslint-disable-next-line no-restricted-globals -- 统一鉴权封装：fetch 的唯一合法出处（非 SSE 与非流式调用统一走这里）
  const res = await fetch(url, { ...options, headers })
  // Task #720：与 request() 同源的全局 401 兜底。修复前裸 fetch 调用（上传/预览/质检/SSE）
  // 全部绕过会话治理，坏 token 能进页面、失败后原地留着让用户反复点"重试"。
  if (res.status === 401 && !isAuthEndpoint(url)) {
    handleSessionExpired()
    throw new ApiError(401, '登录状态已失效，正在跳转重新登录；待上传文件已保留，登录后会自动继续')
  }
  return res
}

export async function request<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // eslint-disable-next-line no-restricted-globals -- 标准请求封装：fetch 的唯一合法出处，其余调用点必须走 request()/http
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (!res.ok) {
    // 全局 401 兜底：与 authorizedFetch 共用同一套会话治理（Task #720）
    if (res.status === 401 && !isAuthEndpoint(`${API_BASE}${path}`)) {
      handleSessionExpired()
      throw new ApiError(401, '登录已过期，请重新登录')
    }
    let detail = `请求失败(${res.status})`
    try {
      const body = await res.json()
      detail = detailText(body?.detail, detail)
    } catch {
      /* 非 JSON 响应，忽略 */
    }
    throw new ApiError(res.status, detail)
  }

  const text = await res.text()
  return (text ? JSON.parse(text) : {}) as T
}

export const http = {
  get: <T = any>(path: string, params?: Record<string, any>) => {
    const query = params
      ? '?' +
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== null && v !== '')
          .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
          .join('&')
      : ''
    return request<T>(path + query)
  },
  post: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T = any>(path: string, params?: Record<string, any>) => {
    const query = params
      ? '?' +
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== null && v !== '')
          .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
          .join('&')
      : ''
    return request<T>(path + query, { method: 'DELETE' })
  },
  patch: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
}