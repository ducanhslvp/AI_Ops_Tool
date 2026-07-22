import { createFileRoute } from '@tanstack/react-router'
import { AiChatPage } from '@/features/aiops/ai-chat'

export const Route = createFileRoute('/_authenticated/chats/')({
  component: AiChatPage,
})
