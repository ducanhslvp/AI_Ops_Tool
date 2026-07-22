import { createFileRoute } from '@tanstack/react-router'
import { PlatformSettingsPage } from '@/features/aiops/platform-settings'

export const Route = createFileRoute('/_authenticated/settings/notifications')({
  component: () => <PlatformSettingsPage section='notifications' />,
})
