import { createFileRoute } from '@tanstack/react-router'
import { PlatformSettingsPage } from '@/features/aiops/platform-settings'

export const Route = createFileRoute('/_authenticated/settings/templates')({
  component: () => <PlatformSettingsPage section='report-templates' />,
})
