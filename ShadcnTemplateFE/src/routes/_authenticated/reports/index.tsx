import { createFileRoute } from '@tanstack/react-router'
import { ReportsPage } from '@/features/aiops/reports'

export const Route = createFileRoute('/_authenticated/reports/')({
  component: ReportsPage,
})

