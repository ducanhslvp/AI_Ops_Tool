import { createFileRoute } from '@tanstack/react-router'
import { ServerDetailRoute } from '@/features/aiops/server-detail'

export const Route = createFileRoute('/_authenticated/inventory/servers/$serverId')({
  component: ServerDetailRoute,
})
