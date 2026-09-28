/**
 * 统一 API 请求封装
 * 自动注入 token(Authorization: Bearer)、解析错误、处理 JSON
 */
export const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
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
  return fetch(url, { ...options, headers })
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
    // 全局 401 兜底：令牌无效或已过期 → 清除本地凭证并回登录页
    // （避免各页面各自弹 error 后停留在空白/空态）
    if (res.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      const redirect = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.replace(`/login?redirect=${redirect}`)
      throw new ApiError(401, '登录已过期，请重新登录')
    }
    let detail = `请求失败(${res.status})`
    try {
      const body = await res.json()
      detail = body?.detail || detail
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