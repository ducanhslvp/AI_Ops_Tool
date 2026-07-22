const ACCESS_TOKEN_KEY = 'aiops_access_token'
const REFRESH_TOKEN_KEY = 'aiops_refresh_token'

let accessToken = window.sessionStorage.getItem(ACCESS_TOKEN_KEY) ?? ''

export function getAccessToken() {
  return accessToken
}

export function isAccessTokenFresh(skewSeconds = 30) {
  if (!accessToken) return false
  try {
    const payload = accessToken.split('.')[1]
    if (!payload) return false
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const normalized = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    const decoded = JSON.parse(window.atob(normalized)) as { exp?: number }
    return typeof decoded.exp === 'number' && decoded.exp > Date.now() / 1000 + skewSeconds
  } catch {
    return false
  }
}

export function getRefreshToken() {
  return (
    window.localStorage.getItem(REFRESH_TOKEN_KEY) ??
    window.sessionStorage.getItem(REFRESH_TOKEN_KEY) ??
    ''
  )
}

export function storeTokens(
  access: string,
  refresh: string,
  remember: boolean
) {
  accessToken = access
  window.sessionStorage.setItem(ACCESS_TOKEN_KEY, access)
  window.localStorage.removeItem(REFRESH_TOKEN_KEY)
  window.sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  const storage = remember ? window.localStorage : window.sessionStorage
  storage.setItem(REFRESH_TOKEN_KEY, refresh)
}

export function updateRotatedTokens(access: string, refresh: string) {
  const remember = window.localStorage.getItem(REFRESH_TOKEN_KEY) !== null
  storeTokens(access, refresh, remember)
}

export function clearTokens() {
  accessToken = ''
  window.sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  window.sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  window.localStorage.removeItem(REFRESH_TOKEN_KEY)
}
