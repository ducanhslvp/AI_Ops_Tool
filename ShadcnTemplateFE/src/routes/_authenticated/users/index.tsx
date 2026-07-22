import { createFileRoute } from '@tanstack/react-router'
import { UserAdminPage } from '@/features/aiops/user-admin'

export const Route = createFileRoute('/_authenticated/users/')({
  component: UserAdminPage,
})
