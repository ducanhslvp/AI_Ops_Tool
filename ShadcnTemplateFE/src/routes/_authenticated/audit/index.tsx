import { createFileRoute } from '@tanstack/react-router'
import { AuditPage } from '@/features/aiops/audit'

export const Route = createFileRoute('/_authenticated/audit/')({
  component: AuditPage,
})

