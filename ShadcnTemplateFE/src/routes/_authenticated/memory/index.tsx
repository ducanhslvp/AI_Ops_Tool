import { createFileRoute } from '@tanstack/react-router'
import { MemoryPage } from '@/features/aiops/memory'

export const Route = createFileRoute('/_authenticated/memory/')({ component: MemoryPage })
