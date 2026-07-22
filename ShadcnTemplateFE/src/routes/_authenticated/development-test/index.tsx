import { createFileRoute } from '@tanstack/react-router'
import { DevelopmentTestPage } from '@/features/aiops/development-test'

export const Route = createFileRoute('/_authenticated/development-test/')({ component: DevelopmentTestPage })
