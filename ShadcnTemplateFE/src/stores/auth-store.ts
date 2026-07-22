import { create } from 'zustand'
import { clearTokens, getAccessToken, storeTokens } from '@/lib/auth-tokens'

export interface AuthUser {
  id: string
  email: string
  full_name: string
  is_active: boolean
  role: {
    name: string
    permissions: Array<{ code: string; description: string }>
  }
}

interface AuthState {
  auth: {
    user: AuthUser | null
    accessToken: string
    setUser: (user: AuthUser | null) => void
    setSession: (
      accessToken: string,
      refreshToken: string,
      remember: boolean
    ) => void
    setAccessToken: (accessToken: string) => void
    resetAccessToken: () => void
    reset: () => void
  }
}

export const useAuthStore = create<AuthState>()((set) => ({
  auth: {
    user: null,
    accessToken: getAccessToken(),
    setUser: (user) =>
      set((state) => ({ ...state, auth: { ...state.auth, user } })),
    setSession: (accessToken, refreshToken, remember) => {
      storeTokens(accessToken, refreshToken, remember)
      set((state) => ({ ...state, auth: { ...state.auth, accessToken } }))
    },
    setAccessToken: (accessToken) =>
      set((state) => ({ ...state, auth: { ...state.auth, accessToken } })),
    resetAccessToken: () => {
      clearTokens()
      set((state) => ({ ...state, auth: { ...state.auth, accessToken: '' } }))
    },
    reset: () => {
      clearTokens()
      set((state) => ({
        ...state,
        auth: { ...state.auth, user: null, accessToken: '' },
      }))
    },
  },
}))
