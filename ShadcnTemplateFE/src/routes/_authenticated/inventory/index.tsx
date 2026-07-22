import { createFileRoute } from '@tanstack/react-router'
import { InventoryPage } from '@/features/aiops/inventory'

export const Route = createFileRoute('/_authenticated/inventory/')({
  component: InventoryPage,
})

