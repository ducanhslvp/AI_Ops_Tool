import { createFileRoute } from '@tanstack/react-router'
import { PolicyPage } from '@/features/aiops/policy'

export const Route = createFileRoute('/_authenticated/policy/')({
  component: PolicyPage,
})

