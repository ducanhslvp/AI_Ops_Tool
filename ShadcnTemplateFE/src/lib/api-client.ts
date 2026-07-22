import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isAccessTokenFresh,
  updateRotatedTokens,
} from './auth-tokens'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface PaginatedResult<T> {
  items: T[]
  total: number
}

export async function getPaginated<T>(
  path: string,
  params: Record<string, string | number | undefined>
): Promise<PaginatedResult<T>> {
  const response = await apiClient.get<T[]>(path, { params })
  const total = Number(response.headers['x-total-count'] ?? response.data.length)
  return { items: response.data, total: Number.isFinite(total) ? total : response.data.length }
}

apiClient.interceptors.request.use(async (config) => {
  if (!isAccessTokenFresh() && getRefreshToken()) {
    try {
      refreshPromise ??= rotateRefreshToken().finally(() => {
        refreshPromise = null
      })
      await refreshPromise
    } catch (error) {
      clearTokens()
      return Promise.reject(error)
    }
  }
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

type RetryRequest = InternalAxiosRequestConfig & { _retry?: boolean }
let refreshPromise: Promise<string> | null = null

async function rotateRefreshToken(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) throw new Error('No refresh token')
  const { data } = await axios.post<{
    access_token: string
    refresh_token: string
  }>(`${API_BASE_URL}/auth/refresh`, { refresh_token: refreshToken })
  updateRotatedTokens(data.access_token, data.refresh_token)
  return data.access_token
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config as RetryRequest | undefined
    const isAuthEndpoint = request?.url?.includes('/auth/')
    if (
      error.response?.status !== 401 ||
      !request ||
      request._retry ||
      isAuthEndpoint
    ) {
      return Promise.reject(error)
    }
    request._retry = true
    try {
      refreshPromise ??= rotateRefreshToken().finally(() => {
        refreshPromise = null
      })
      const token = await refreshPromise
      request.headers.Authorization = `Bearer ${token}`
      return apiClient(request)
    } catch (refreshError) {
      clearTokens()
      return Promise.reject(refreshError)
    }
  }
)

export async function ensureAccessToken() {
  if (isAccessTokenFresh()) return true
  if (!getRefreshToken()) return false
  try {
    refreshPromise ??= rotateRefreshToken().finally(() => {
      refreshPromise = null
    })
    await refreshPromise
    return true
  } catch {
    clearTokens()
    return false
  }
}

export interface ServerSentEvent<T = unknown> {
  event: string
  data: T
}

export async function postEventStream<T>(
  path: string,
  body: unknown,
  onEvent: (event: ServerSentEvent<T>) => void,
  signal?: AbortSignal
) {
  if (!(await ensureAccessToken())) throw new Error('Session expired')
  const request = () => fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${getAccessToken()}`,
      },
      body: JSON.stringify(body),
      signal,
    })
  let response = await request()
  if (response.status === 401 && getRefreshToken()) {
    refreshPromise ??= rotateRefreshToken().finally(() => {
      refreshPromise = null
    })
    await refreshPromise
    response = await request()
  }
  if (!response.ok || !response.body) {
    let detail = `Streaming request failed with HTTP ${response.status}`
    try {
      const payload = await response.json() as { detail?: string; error?: { message?: string } }
      detail = payload.detail ?? payload.error?.message ?? detail
    } catch {
      // Preserve the HTTP fallback when the edge returns a non-JSON response.
    }
    throw new Error(detail)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const event = frame.match(/^event:\s*(.+)$/m)?.[1] ?? 'message'
      const data = frame.match(/^data:\s*(.+)$/m)?.[1]
      if (data) onEvent({ event, data: JSON.parse(data) as T })
    }
    if (done) break
  }
}
