import { createFileRoute, redirect } from '@tanstack/react-router'
import { apiClient, ensureAccessToken } from '@/lib/api-client'
import { type AuthUser, useAuthStore } from '@/stores/auth-store'
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: async ({ location }) => {
    if (!(await ensureAccessToken())) {
      throw redirect({
        to: '/sign-in',
        search: { redirect: location.href },
      })
    }
    const auth = useAuthStore.getState().auth
    if (!auth.user) {
      try {
        const user = (await apiClient.get<AuthUser>('/auth/me')).data
        auth.setUser(user)
      } catch {
        auth.reset()
        throw redirect({
          to: '/sign-in',
          search: { redirect: location.href },
        })
      }
    }
  },
  component: AuthenticatedLayout,
})
