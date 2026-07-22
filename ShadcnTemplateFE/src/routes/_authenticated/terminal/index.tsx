import { createFileRoute } from '@tanstack/react-router'
import { TerminalPage } from '@/features/aiops/terminal'

export const Route = createFileRoute('/_authenticated/terminal/')({
  component: TerminalPage,
})

