import { createFileRoute } from '@tanstack/react-router'
import { DiscoveryPage } from '@/features/aiops/discovery'

export const Route = createFileRoute('/_authenticated/discovery/')({ component: DiscoveryPage })
