import z from 'zod'
import { createFileRoute, redirect } from '@tanstack/react-router'

const appsSearchSchema = z.object({
  type: z.enum(['all', 'connected', 'notConnected']).optional().catch(undefined),
  filter: z.string().optional().catch(''),
  sort: z.enum(['asc', 'desc']).optional().catch(undefined),
})

export const Route = createFileRoute('/_authenticated/apps/')({
  validateSearch: appsSearchSchema,
  beforeLoad: () => {
    throw redirect({ to: '/settings/appearance' })
  },
})
