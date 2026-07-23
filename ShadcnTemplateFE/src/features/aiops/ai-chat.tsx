import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot, Brain, CheckCircle2, CircleAlert, Clock3, Database, Download, Eraser, Eye, MessageSquare, Pencil,
  Plus, RefreshCw, Search as SearchIcon, Send, Sparkles, Square, Trash2, Wrench,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { apiClient, postEventStream } from '@/lib/api-client'
import { useIsDesktop } from '@/hooks/use-desktop'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SearchableSelect } from '@/components/searchable-select'
import { QueryLoadError } from '@/components/query-load-error'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import type { TargetEnvironment, TargetServer, TargetSystem } from '@/components/server-target-selector'

interface ChatResponse {
  session_id: string
  request_id: string
  provider: string
  model: string
  answer: string
  plan: string[]
  executed_tools: ToolEvent[]
  confidence: { score: number; reason: string; need_more_data: boolean }
}

interface ToolEvent {
  id?: string
  tool: string
  arguments?: Record<string, unknown>
  result?: { decision?: string; approval_id?: string; command?: string; error?: string; stdout?: string; exit_code?: number }
}

interface StreamEvent {
  type: string
  delta?: string
  request_id: string
  data?: ChatResponse | Record<string, unknown>
}

interface SessionRecord {
  id: string
  system_id: string
  title: string
  status: string
  last_activity_at?: string
  updated_at: string
  model?: string | null
  reasoning_effort: ReasoningEffort
  include_full_memory: boolean
  bypass_policy: boolean
}

interface SessionDetail extends SessionRecord {
  messages_has_more: boolean
  messages: Array<{ id: string; role: string; content: string; created_at: string }>
}
interface MessagePage {
  items: Array<{ id: string; role: string; content: string; created_at: string }>
  has_more: boolean
  next_before?: string | null
}

interface TimelineEvent {
  id: string
  type: string
  label: string
  detail?: string
  state: 'running' | 'complete' | 'attention' | 'failed'
  occurredAt: Date
}

interface RuntimeStatus {
  active_provider: string
  exclusive_mode: boolean
  health?: { status: string; detail?: string; version?: string }
  models: string[]
  model_catalog: ModelCatalogItem[]
  reasoning_efforts: ReasoningEffort[]
}

type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max' | 'ultra'

interface ModelCatalogItem {
  id: string
  display_name: string
  description: string
  is_default: boolean
  default_reasoning_effort: ReasoningEffort
  reasoning_efforts: ReasoningEffort[]
}

interface WorkspaceOverview {
  system: { id: string; code: string; name: string }
  workspace_path: string
  file_count: number
  files: Array<{ path: string; size: number; deletable: boolean }>
  memory_count: number
  memories: Array<{ id: string; category: string; topic: string; summary: string; occurred_at: string }>
}
interface WorkspacePreview { path: string; previewable: boolean; content: string; size: number; truncated?: boolean }

interface CommandConsentResult { decision: string; approval_id?: string; stdout?: string; stderr?: string; exit_code?: number; error?: string; consent_scope?: string }

export function AiChatPage() {
  const isDesktop = useIsDesktop()
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [systemId, setSystemId] = useState('')
  const [environmentId, setEnvironmentId] = useState('')
  const [serverId, setServerId] = useState('')
  const [sessionId, setSessionId] = useState<string>()
  const [sessionSearch, setSessionSearch] = useState('')
  const [messages, setMessages] = useState<Array<{ id: string; role: string; text: string; createdAt?: string }>>([])
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [lastResult, setLastResult] = useState<ChatResponse>()
  const [controller, setController] = useState<AbortController>()
  const [activeRequestId, setActiveRequestId] = useState<string>()
  const [model, setModel] = useState('')
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('medium')
  const [includeFullMemory, setIncludeFullMemory] = useState(false)
  const [bypassPolicy, setBypassPolicy] = useState(false)
  const [bypassWarningOpen, setBypassWarningOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [clearMemoryOpen, setClearMemoryOpen] = useState(false)
  const [clearMemoryConfirmation, setClearMemoryConfirmation] = useState('')
  const [commandConsent, setCommandConsent] = useState<{ id: string; command: string; hostname?: string }>()
  const [workspacePreview, setWorkspacePreview] = useState<WorkspacePreview>()
  const [hasOlderMessages, setHasOlderMessages] = useState(false)
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false)
  const conversationScrollRef = useRef<HTMLDivElement>(null)
  const timelineScrollRef = useRef<HTMLDivElement>(null)
  const commandDecisionSubmittingRef = useRef(false)
  const prependingMessagesRef = useRef(false)

  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems', 'chat'], queryFn: async () =>
    (await apiClient.get<TargetSystem[]>('/inventory/systems', { params: { page: 1, page_size: 200 } })).data })
  const environmentsQuery = useQuery({ queryKey: ['inventory', 'environments', 'chat'], queryFn: async () =>
    (await apiClient.get<TargetEnvironment[]>('/inventory/environments', { params: { page: 1, page_size: 200 } })).data })
  const serversQuery = useQuery({ queryKey: ['inventory', 'servers', 'chat'], queryFn: async () =>
    (await apiClient.get<TargetServer[]>('/inventory/servers', { params: { page: 1, page_size: 200 } })).data })
  const sessionsQuery = useQuery({
    queryKey: ['ai', 'sessions', systemId], enabled: Boolean(systemId),
    queryFn: async () => (await apiClient.get<SessionRecord[]>('/ai/sessions', {
      params: { system_id: systemId, page: 1, page_size: 200 },
    })).data,
    refetchOnMount: 'always',
  })
  const runtimeQuery = useQuery({
    queryKey: ['ai', 'runtime'], staleTime: 60_000, retry: 1,
    queryFn: async () => {
      const [runtime, health] = await Promise.all([
        apiClient.get<Omit<RuntimeStatus, 'health'>>('/ai/providers'),
        apiClient.get<{ providers: Array<{ provider: string; status: string; detail?: string; version?: string }> }>('/ai/providers/health'),
      ])
      return { ...runtime.data, health: health.data.providers.find((item) => item.provider === runtime.data.active_provider) } satisfies RuntimeStatus
    },
  })
  const workspaceQuery = useQuery({
    queryKey: ['ai', 'workspace', systemId], enabled: workspaceOpen && Boolean(systemId),
    queryFn: async () => (await apiClient.get<WorkspaceOverview>(`/ai/systems/${systemId}/workspace`)).data,
  })
  const codexUnavailable = runtimeQuery.data?.health && runtimeQuery.data.health.status !== 'ready'
  const availableEnvironments = useMemo(() => {
    const ids = new Set((serversQuery.data ?? []).filter((item) => item.system_id === systemId).map((item) => item.environment_id))
    return (environmentsQuery.data ?? []).filter((item) => ids.has(item.id))
  }, [environmentsQuery.data, serversQuery.data, systemId])
  const availableServers = useMemo(() => (serversQuery.data ?? []).filter((item) =>
    item.system_id === systemId && (!environmentId || item.environment_id === environmentId)
  ), [serversQuery.data, systemId, environmentId])
  const filteredSessions = (sessionsQuery.data ?? []).filter((item) =>
    item.title.toLowerCase().includes(sessionSearch.trim().toLowerCase()))
  const preferredModel = (runtimeQuery.data?.model_catalog ?? []).find((item) => item.is_default)
    ?? runtimeQuery.data?.model_catalog?.[0]
  const effectiveModel = model || preferredModel?.id || ''
  const selectedModel = (runtimeQuery.data?.model_catalog ?? []).find((item) => item.id === effectiveModel)
  const reasoningEfforts = selectedModel?.reasoning_efforts.length
    ? selectedModel.reasoning_efforts
    : (runtimeQuery.data?.reasoning_efforts ?? ['low', 'medium', 'high'])

  const createSession = useMutation({
    mutationFn: async () => (await apiClient.post<SessionRecord>('/ai/sessions', {
      system_id: systemId, title: 'New conversation', model: effectiveModel || null,
      reasoning_effort: reasoningEffort, include_full_memory: includeFullMemory,
    })).data,
    onSuccess: (session) => {
      queryClient.setQueryData<SessionRecord[]>(['ai', 'sessions', systemId], (current) => [session, ...(current ?? [])])
      setSessionId(session.id); setBypassPolicy(false); setMessages([]); setHasOlderMessages(false); setTimeline([]); setLastResult(undefined)
    },
    onError: () => toast.error('Conversation could not be created.'),
  })
  const refreshWorkspace = useMutation({
    mutationFn: async () => apiClient.post(`/ai/systems/${systemId}/workspace/refresh`),
    onSuccess: async () => { await workspaceQuery.refetch(); toast.success('Workspace rebuilt. Codex will reload it on the next request.') },
    onError: () => toast.error('Workspace could not be refreshed.'),
  })
  const clearMemory = useMutation({
    mutationFn: async () => apiClient.post(`/ai/systems/${systemId}/reset-memory`, {
      confirm_system_code: clearMemoryConfirmation,
    }),
    onSuccess: async () => {
      setClearMemoryOpen(false); setClearMemoryConfirmation('')
      await workspaceQuery.refetch()
      void queryClient.invalidateQueries({ queryKey: ['ai', 'sessions', systemId] })
      toast.success('System memory was cleared from the database and workspace.')
    },
    onError: () => toast.error('System memory could not be cleared.'),
  })
  const previewWorkspaceFile = useMutation({ mutationFn: async (path: string) =>
    (await apiClient.get<WorkspacePreview>(`/ai/systems/${systemId}/workspace/file/preview`, { params: { path } })).data,
    onSuccess: setWorkspacePreview, onError: () => toast.error('Workspace file preview could not be loaded.') })
  const deleteWorkspaceFile = useMutation({ mutationFn: async (path: string) => apiClient.delete(`/ai/systems/${systemId}/workspace/file`, { params: { path } }),
    onSuccess: async () => { await workspaceQuery.refetch(); toast.success('Workspace file deleted.') },
    onError: () => toast.error('This file is protected or could not be deleted.') })
  const deleteMemory = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/ai/systems/${systemId}/memories/${id}`),
    onSuccess: async () => { await workspaceQuery.refetch(); toast.success('Memory entry deleted from the database and workspace.') },
    onError: () => toast.error('Memory entry could not be deleted.') })
  const downloadWorkspaceFile = async (path: string) => { try { const response = await apiClient.get(`/ai/systems/${systemId}/workspace/file/download`, { params: { path }, responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = path.split('/').pop() ?? 'workspace-file'; link.click(); URL.revokeObjectURL(url)
  } catch { toast.error('Workspace file could not be downloaded.') } }
  const decideCommand = useMutation({
    mutationFn: async (decision: 'accept' | 'reject' | 'accept_session' | 'accept_command') =>
      (await apiClient.post<CommandConsentResult>(`/ai/command-consents/${commandConsent?.id}/decision`, { decision })).data,
    onSuccess: (result) => {
      setCommandConsent(undefined)
      setTimeline((current) => [...current.map((item) => item.state === 'running' ? { ...item, state: 'complete' as const } : item), {
        id: `consent-${Date.now()}`, type: 'command_consent_decided',
        label: result.decision === 'rejected' ? 'SSH command rejected' : 'SSH command consent accepted',
        detail: result.stdout ?? result.error ?? `Exit code ${result.exit_code ?? '-'}`,
        state: result.decision === 'rejected' ? 'attention' : 'complete', occurredAt: new Date(),
      }])
    },
    onError: () => toast.error('The command consent decision could not be applied.'),
    onSettled: () => { commandDecisionSubmittingRef.current = false },
  })
  const changeBypass = useMutation({
    mutationFn: async (enabled: boolean) => (await apiClient.put<{ bypass_policy: boolean }>(
      `/ai/sessions/${sessionId}/policy-bypass`, { enabled }
    )).data,
    onSuccess: (data) => {
      setBypassPolicy(data.bypass_policy)
      setBypassWarningOpen(false)
      toast[data.bypass_policy ? 'warning' : 'success'](
        data.bypass_policy ? 'Session-only Policy bypass enabled. Every SSH action is still audited.' : 'Policy enforcement restored.'
      )
    },
    onError: () => toast.error('Your role does not have the ai:policy_bypass permission.'),
  })
  const submitCommandDecision = (decision: 'accept' | 'reject' | 'accept_session' | 'accept_command') => {
    if (commandDecisionSubmittingRef.current || decideCommand.isPending) return
    commandDecisionSubmittingRef.current = true
    decideCommand.mutate(decision)
  }
  const deleteSession = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/ai/sessions/${id}`),
    onSuccess: (_response, id) => {
      void queryClient.invalidateQueries({ queryKey: ['ai', 'sessions', systemId] })
      if (sessionId === id) { setSessionId(undefined); setMessages([]); setTimeline([]); setLastResult(undefined) }
      toast.success('Conversation deleted.')
    },
  })
  const renameSession = useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => apiClient.patch(`/ai/sessions/${id}`, { title }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai', 'sessions', systemId] }),
  })

  const loadSession = async (selectedId: string) => {
    if (chat.isPending) return
    setSessionId(selectedId); setHasOlderMessages(false); setLastResult(undefined); setTimeline([])
    try {
      const detail = (await apiClient.get<SessionDetail>(`/ai/sessions/${selectedId}`)).data
      setModel(detail.model ?? ''); setReasoningEffort(detail.reasoning_effort ?? 'medium')
      setIncludeFullMemory(detail.include_full_memory ?? false)
      setBypassPolicy(detail.bypass_policy ?? false)
      setHasOlderMessages(detail.messages_has_more)
      setMessages(detail.messages.map((item) => ({
        id: item.id, role: item.role, text: item.content, createdAt: item.created_at,
      })))
    } catch { toast.error('Chat history could not be loaded.') }
  }

  const loadOlderMessages = async () => {
    const container = conversationScrollRef.current
    const oldest = messages[0]
    if (!sessionId || !oldest?.createdAt || !hasOlderMessages || loadingOlderMessages || !container) return
    const previousHeight = container.scrollHeight
    prependingMessagesRef.current = true
    setLoadingOlderMessages(true)
    try {
      const page = (await apiClient.get<MessagePage>(`/ai/sessions/${sessionId}/messages`, {
        params: { before: oldest.createdAt, before_id: oldest.id, limit: 50 },
      })).data
      setHasOlderMessages(page.has_more)
      setMessages((current) => {
        const existing = new Set(current.map((item) => item.id))
        const older = page.items.filter((item) => !existing.has(item.id)).map((item) => ({
          id: item.id, role: item.role, text: item.content, createdAt: item.created_at,
        }))
        return [...older, ...current]
      })
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          container.scrollTop += container.scrollHeight - previousHeight
          prependingMessagesRef.current = false
        })
      })
    } catch {
      prependingMessagesRef.current = false
      toast.error('Older messages could not be loaded.')
    } finally {
      setLoadingOlderMessages(false)
    }
  }

  const appendTimeline = (event: StreamEvent) => {
    const data = (event.data ?? {}) as Record<string, unknown>
    if (event.type === 'command_consent_required' && data.approval_id) {
      setCommandConsent({ id: String(data.approval_id), command: String(data.command ?? 'Command details unavailable'), hostname: data.hostname ? String(data.hostname) : undefined })
    }
    const details = event.type === 'context_ready'
      ? `${Number(data.context_size ?? 0).toLocaleString()} characters from ${Array.isArray(data.sources) ? data.sources.length : 0} sources`
      : event.type === 'tool_call' ? JSON.stringify(data.arguments ?? {})
      : event.type === 'prompt_prepared' ? String(data.prompt ?? '')
      : event.type === 'provider_input' ? `${Number(data.characters ?? 0).toLocaleString()} characters\n${String(data.prompt ?? '')}`
      : event.type === 'codex_status' ? String(data.status ?? '')
      : event.type === 'codex_activity' ? `${String(data.activity ?? '')}: ${String(data.detail ?? '')}`
      : event.type === 'codex_output' ? String(data.text ?? '')
      : event.type === 'command_consent_required' ? `${String(data.hostname ?? data.server_id ?? 'Server')}\n${String(data.command ?? '')}`
      : event.type === 'tool_result' ? String((data.result as Record<string, unknown> | undefined)?.decision ?? (data.result as Record<string, unknown> | undefined)?.error ?? 'Result received')
      : event.type === 'provider_completed' ? `${String(data.provider ?? 'AI')} / ${String(data.model ?? 'model')}`
      : String(data.label ?? '')
    const labels: Record<string, string> = {
      started: 'Request accepted', session_ready: 'Conversation context loaded', context_started: 'Building System workspace context',
      context_ready: 'Workspace context ready', provider_started: `AI provider round ${String(data.round ?? '')}`,
      prompt_prepared: `Prompt prepared / ${String(data.reasoning_effort ?? 'medium')} effort`,
      provider_input: 'Exact prompt sent to Codex CLI',
      codex_status: 'Codex CLI status', codex_activity: 'Codex CLI workspace activity',
      codex_output: 'Codex CLI output',
      command_consent_required: 'Waiting for SSH command approval',
      provider_completed: 'AI response received', tool_call: `Calling ${String(data.tool ?? 'registered tool')}`,
      tool_result: `${String(data.tool ?? 'Tool')} completed`, audit_started: 'Recording immutable audit evidence',
      persistence_completed: 'Conversation, memory and audit saved', error: 'Request failed',
    }
    setTimeline((current) => {
      const completed = current.map((item) => item.state === 'running' ? { ...item, state: 'complete' as const } : item)
      return [...completed, {
        id: `${event.type}-${event.request_id}-${completed.length}`, type: event.type,
        label: labels[event.type] ?? event.type,
        detail: details && details !== (labels[event.type] ?? event.type) ? details : undefined,
        state: event.type === 'error' ? 'failed' : event.type === 'command_consent_required' || event.type === 'tool_result' && details.includes('approval') ? 'attention' : 'running',
        occurredAt: new Date(),
      }]
    })
  }

  const chat = useMutation({
    mutationFn: async ({ message, display }: { message: string; display: boolean }) => {
      const abortController = new AbortController(); setController(abortController)
      let activeSessionId = sessionId
      if (!activeSessionId) {
        const created = (await apiClient.post<SessionRecord>('/ai/sessions', { system_id: systemId, title: message.slice(0, 80), model: effectiveModel || null, reasoning_effort: reasoningEffort, include_full_memory: includeFullMemory })).data
        activeSessionId = created.id; setSessionId(created.id)
      }
      let result: ChatResponse | undefined
      let streamError = ''
      await postEventStream<StreamEvent>('/ai/chat/stream', {
        message, session_id: activeSessionId, system_id: systemId, server_id: serverId || null,
        model: effectiveModel || null, reasoning_effort: reasoningEffort, include_full_memory: includeFullMemory,
        internal_continuation: !display,
      }, ({ data: event }) => {
        if (event.type === 'started') setActiveRequestId(event.request_id)
        if (event.type === 'heartbeat') return
        if (!['content_delta', 'completed'].includes(event.type)) appendTimeline(event)
        if (event.type === 'content_delta' && event.delta) setMessages((current) => current.map((item, index) =>
          index === current.length - 1 ? { ...item, text: item.text + event.delta } : item))
        if (event.type === 'completed') result = event.data as ChatResponse
        if (event.type === 'error') streamError = String((event.data as Record<string, unknown> | undefined)?.message ?? 'AI request failed')
      }, abortController.signal)
      if (streamError) throw new Error(streamError)
      if (!result) throw new Error('Stream completed without a result')
      return result
    },
    onMutate: ({ message, display }) => {
      const now = new Date().toISOString(); if (display) setTimeline([])
      setMessages((current) => [...current,
        ...(display ? [{ id: `user-${Date.now()}`, role: 'user', text: message, createdAt: now }] : []),
        { id: `assistant-${Date.now()}`, role: 'assistant', text: '', createdAt: now },
      ]); if (display) setInput('')
    },
    onSuccess: (result) => {
      setSessionId(result.session_id); setLastResult(result)
      setTimeline((current) => current.map((item) => item.state === 'running' ? { ...item, state: 'complete' } : item))
      void queryClient.invalidateQueries({ queryKey: ['ai', 'sessions', systemId] })
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, text: result.answer } : item))
    },
    onError: (error) => {
      setMessages((current) => current.map((item, index) => index === current.length - 1 && !item.text
        ? { ...item, text: 'The request could not be completed. Review the execution timeline and try again.' } : item))
      toast.error(error instanceof Error ? error.message : 'AI orchestration request failed.')
    },
    onSettled: () => { setController(undefined); setActiveRequestId(undefined) },
  })

  const submit = () => {
    const message = input.trim()
    if (message.length < 2 || chat.isPending || !systemId) return
    chat.mutate({ message, display: true })
  }

  useEffect(() => {
    const container = conversationScrollRef.current
    if (!container) return
    const scrollToLatest = () => {
      if (!prependingMessagesRef.current) container.scrollTop = container.scrollHeight
    }
    const observer = new MutationObserver(scrollToLatest)
    observer.observe(container, { childList: true, subtree: true, characterData: true })
    const frame = window.requestAnimationFrame(scrollToLatest)
    return () => { observer.disconnect(); window.cancelAnimationFrame(frame) }
  }, [sessionId])

  useEffect(() => {
    const container = timelineScrollRef.current
    if (!container) return
    const frame = window.requestAnimationFrame(() => { container.scrollTop = container.scrollHeight })
    return () => window.cancelAnimationFrame(frame)
  }, [timeline, lastResult])

  const selectSystem = (next: string) => {
    setSystemId(next); setEnvironmentId(''); setServerId(''); setSessionId(undefined)
    setMessages([]); setHasOlderMessages(false); setTimeline([]); setLastResult(undefined)
    setModel(runtimeQuery.data?.models[0] ?? ''); setReasoningEffort('medium'); setIncludeFullMemory(false); setBypassPolicy(false)
  }

  const persistRuntime = (values: Record<string, unknown>) => {
    if (sessionId) void apiClient.patch(`/ai/sessions/${sessionId}`, values).then(() =>
      queryClient.invalidateQueries({ queryKey: ['ai', 'sessions', systemId] }))
  }

  const contextPanel = <Card className='flex h-full min-h-0 flex-col rounded-none border-0 shadow-none'>
    <CardHeader className='space-y-3 border-b px-4 py-3'>
      <CardTitle className='text-base'>Conversations</CardTitle>
      <SearchableSelect ariaLabel='System conversation scope' value={systemId} placeholder='Select system first'
        searchPlaceholder='Search systems...' options={(systemsQuery.data ?? []).map((item) => ({ value: item.id, label: `${item.code} - ${item.name}` }))}
        onValueChange={selectSystem} />
      <div className='flex gap-2'>
        <div className='relative min-w-0 flex-1'><SearchIcon className='absolute left-2.5 top-2.5 size-4 text-muted-foreground' />
          <Input className='pl-8' value={sessionSearch} onChange={(event) => setSessionSearch(event.target.value)} placeholder='Search conversations...' /></div>
        <Tooltip><TooltipTrigger asChild><Button size='icon' onClick={() => createSession.mutate()} disabled={!systemId || createSession.isPending} aria-label='New conversation'><Plus className='size-4' /></Button></TooltipTrigger><TooltipContent>New conversation</TooltipContent></Tooltip>
      </div>
    </CardHeader>
    <CardContent className='flex min-h-0 flex-1 flex-col p-0'>
      <div className='min-h-0 flex-1 overflow-auto p-2'>
        {!systemId ? <EmptySidebar text='Select a System to view its conversations.' /> : sessionsQuery.isLoading ? <EmptySidebar text='Loading conversations...' /> : filteredSessions.length === 0 ? <EmptySidebar text='No conversations in this System.' /> :
          filteredSessions.map((session) => <div key={session.id} className={cn('group mb-1 grid grid-cols-[minmax(0,1fr)_auto] items-center rounded-md text-sm hover:bg-accent', session.id === sessionId && 'bg-muted')}>
            <button type='button' onClick={() => void loadSession(session.id)} className='grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-2 px-2 py-2 text-left'>
              <Avatar className='size-8'><AvatarFallback><MessageSquare className='size-4' /></AvatarFallback></Avatar>
              <span className='min-w-0'><span className='block truncate font-medium'>{session.title}</span><span className='block truncate text-xs text-muted-foreground'>{session.status === 'active' ? 'AI is working' : formatRelative(session.last_activity_at ?? session.updated_at)}</span></span>
            </button>
            <span className='flex pe-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100'>
              <Button type='button' variant='ghost' size='icon' className='size-7' aria-label='Rename conversation' onClick={() => { const title = window.prompt('Conversation name', session.title)?.trim(); if (title) renameSession.mutate({ id: session.id, title }) }}><Pencil className='size-3.5' /></Button>
              <Button type='button' variant='ghost' size='icon' className='size-7 text-destructive' aria-label='Delete conversation' onClick={() => { if (window.confirm(`Delete "${session.title}"?`)) deleteSession.mutate(session.id) }}><Trash2 className='size-3.5' /></Button>
            </span>
          </div>)}
      </div>
      <div className='space-y-3 border-t p-4'>
        <p className='text-xs font-medium text-muted-foreground'>Optional execution target</p>
        <SearchableSelect ariaLabel='Target environment' value={environmentId} allowClear disabled={!systemId} placeholder='All environments'
          searchPlaceholder='Search environments...' options={availableEnvironments.map((item) => ({ value: item.id, label: item.name }))}
          onValueChange={(value) => { setEnvironmentId(value); setServerId('') }} />
        <SearchableSelect ariaLabel='Target server' value={serverId} allowClear disabled={!systemId} placeholder='No server selected'
          searchPlaceholder='Search hostname or IP...' options={availableServers.map((item) => ({ value: item.id, label: `${item.hostname} - ${item.ip_address}`, keywords: `${item.os} ${item.role}` }))}
          onValueChange={setServerId} />
      </div>
    </CardContent>
  </Card>

  const conversationPanel = <Card className='flex h-full min-h-0 flex-col rounded-none border-0 shadow-none'>
    <CardHeader className='gap-3 border-b px-4 py-3'>
      <div className='flex items-center justify-between gap-3'><div className='flex min-w-0 items-center gap-3'><Avatar><AvatarFallback><Bot className='size-4' /></AvatarFallback></Avatar><div className='min-w-0'><CardTitle className='truncate text-base'>{(sessionsQuery.data ?? []).find((item) => item.id === sessionId)?.title ?? 'AI Operations Chat'}</CardTitle><p className='truncate text-xs text-muted-foreground'>{systemId ? (systemsQuery.data ?? []).find((item) => item.id === systemId)?.name : 'Select a System to begin'}</p></div></div>
      <div className='flex min-w-0 items-center gap-2 text-xs' title={runtimeQuery.data?.health?.detail}>{codexUnavailable ? <CircleAlert className='size-4 text-destructive' /> : <span className={cn('size-2 rounded-full bg-emerald-500', chat.isPending && 'animate-pulse')} />}<span className='hidden truncate sm:block'>{chat.isPending ? 'AI is answering...' : runtimeQuery.isLoading ? 'Checking AI runtime' : `${runtimeQuery.data?.active_provider ?? 'AI'} ${runtimeQuery.data?.health?.status ?? 'unknown'}`}</span></div></div>
      <div className='flex flex-wrap items-center gap-2'>
        <SearchableSelect className='w-48' ariaLabel='Codex model' value={effectiveModel} allowClear placeholder='Provider default model' searchPlaceholder='Search models...'
          options={(runtimeQuery.data?.model_catalog ?? []).map((item) => ({ value: item.id, label: item.display_name || item.id, keywords: `${item.id} ${item.description}` }))}
          onValueChange={(value) => { const item = runtimeQuery.data?.model_catalog.find((entry) => entry.id === value); const effort = item?.default_reasoning_effort ?? reasoningEffort; setModel(value); setReasoningEffort(effort); persistRuntime({ model: value || null, reasoning_effort: effort }) }} />
        <SearchableSelect className='w-36' ariaLabel='Reasoning effort' value={reasoningEffort}
          options={reasoningEfforts.map((item) => ({ value: item, label: `${item === 'xhigh' ? 'Extra high' : item[0].toUpperCase() + item.slice(1)} effort` }))}
          onValueChange={(value) => { const effort = value as ReasoningEffort; setReasoningEffort(effort); persistRuntime({ reasoning_effort: effort }) }} />
        <label className='flex h-9 items-center gap-2 rounded-md border px-3 text-xs'><Switch checked={includeFullMemory} onCheckedChange={(checked) => { setIncludeFullMemory(checked); persistRuntime({ include_full_memory: checked }) }} /><Brain className='size-3.5' />Full memory</label>
        <label className='flex h-9 items-center gap-2 rounded-md border border-destructive/50 bg-destructive/5 px-3 text-xs text-destructive'>
          <Switch checked={bypassPolicy} disabled={!sessionId || changeBypass.isPending}
            onCheckedChange={(checked) => checked ? setBypassWarningOpen(true) : changeBypass.mutate(false)} />
          Bypass Policy
        </label>
        <Button variant='outline' size='sm' disabled={!systemId} onClick={() => setWorkspaceOpen(true)}><Database className='size-4' />Workspace & memory</Button>
        <Button variant='outline' size='sm' disabled={!systemId} onClick={() => {
          window.location.assign(`/audit?mode=activity&system_id=${encodeURIComponent(systemId)}${serverId ? `&server_id=${encodeURIComponent(serverId)}` : ''}`)
        }}>Audit history</Button>
      </div>
    </CardHeader>
    <CardContent className='flex min-h-0 flex-1 flex-col p-0'>
      <div ref={conversationScrollRef} onScroll={(event) => {
        if (event.currentTarget.scrollTop <= 80) void loadOlderMessages()
      }} className='min-h-0 flex-1 overflow-auto px-4 py-5'>
        {messages.length === 0 ? <div className='grid h-full place-items-center text-center'><div className='max-w-md space-y-2'><Bot className='mx-auto size-9 text-muted-foreground' /><p className='font-medium'>{systemId ? 'Start an operations investigation' : 'Choose a System first'}</p><p className='text-sm text-muted-foreground'>{systemId ? 'A conversation stays scoped to this System and its workspace context.' : 'Conversations, memory and available targets are managed independently for each System.'}</p></div></div> :
          <div className='mx-auto flex w-full max-w-4xl flex-col gap-5'>
            {(hasOlderMessages || loadingOlderMessages) && <Button className='self-center' size='sm' variant='ghost'
              disabled={loadingOlderMessages} onClick={() => void loadOlderMessages()}>
              <RefreshCw className={cn('size-4', loadingOlderMessages && 'animate-spin')} />
              {loadingOlderMessages ? 'Loading earlier messages...' : 'Load earlier messages'}
            </Button>}
            {messages.map((message, index) => <Message key={message.id} role={message.role} text={message.text} createdAt={message.createdAt} pending={chat.isPending && index === messages.length - 1} />)}
          </div>}
      </div>
      <div className='border-t bg-background p-4'><div className='mx-auto max-w-4xl rounded-md border bg-card p-3'>
        <Textarea className='min-h-20 resize-none border-0 p-0 shadow-none focus-visible:ring-0' placeholder={systemId ? 'Ask AI to investigate, explain evidence, or prepare an approved action...' : 'Select a System before sending a message'} disabled={!systemId || Boolean(codexUnavailable)} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} />
        <div className='mt-3 flex items-center justify-between gap-3'><p className='text-xs text-muted-foreground'>{serverId ? `Target: ${availableServers.find((item) => item.id === serverId)?.hostname}` : 'Analysis uses the selected System workspace. Choose a server only when tools need a target.'}</p>
          {chat.isPending ? <Button size='sm' variant='outline' onClick={() => { controller?.abort(); if (activeRequestId) void apiClient.post(`/ai/requests/${activeRequestId}/cancel`) }}><Square className='size-4' />Stop</Button> : <Button size='sm' onClick={submit} disabled={!systemId || input.trim().length < 2 || Boolean(codexUnavailable)}><Send className='size-4' />Send</Button>}
        </div>
      </div></div>
    </CardContent>
  </Card>

  const timelinePanel = <Card className='flex h-full min-h-0 flex-col rounded-none border-0 shadow-none'>
    <CardHeader className='border-b px-4 py-3'><CardTitle className='flex items-center gap-2 text-base'><Sparkles className='size-4' />Execution Timeline</CardTitle><p className='text-xs text-muted-foreground'>{chat.isPending ? 'Live backend activity' : 'Evidence from the latest request'}</p></CardHeader>
    <CardContent ref={timelineScrollRef} className='flex min-h-0 flex-1 flex-col gap-0 overflow-auto p-4'>
      {timeline.length === 0 && !lastResult ? <div className='grid min-h-32 place-items-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground'>Context, provider rounds, tool calls and persistence will appear here.</div> : timeline.map((event, index) => <TimelineItem key={event.id} event={event} last={index === timeline.length - 1} />)}
      {(lastResult?.plan ?? []).map((text) => <div key={text} className='mt-3 rounded-md border p-3'><p className='text-xs font-medium'>Plan</p><p className='mt-1 break-words text-xs text-muted-foreground'>{text}</p></div>)}
      {lastResult && <div className='mt-3 rounded-md border p-3 text-sm'><p className='mb-2 break-all text-xs text-muted-foreground'>{lastResult.provider} / {lastResult.model}</p><p className='font-medium'>Confidence {Math.round(lastResult.confidence.score * 100)}%</p><p className='mt-1 break-words text-xs text-muted-foreground'>{lastResult.confidence.reason}</p>{lastResult.confidence.need_more_data && <p className='mt-2 text-xs text-amber-600 dark:text-amber-400'>More evidence may be required.</p>}</div>}
      <ToolContract />
    </CardContent>
  </Card>

  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main fixed>
    <QueryLoadError visible={systemsQuery.isError || environmentsQuery.isError || serversQuery.isError || sessionsQuery.isError} retrying={systemsQuery.isFetching || environmentsQuery.isFetching || serversQuery.isFetching || sessionsQuery.isFetching} message='Conversation context could not be loaded. Your draft is preserved.' onRetry={() => Promise.all([systemsQuery.refetch(), environmentsQuery.refetch(), serversQuery.refetch(), sessionsQuery.refetch()])} />
    {isDesktop ? <ResizablePanelGroup id='chat-workspace-v2' orientation='horizontal' className='min-h-0 flex-1 overflow-hidden rounded-md border'>
      <ResizablePanel id='chat-context-v2' defaultSize={300} minSize={260} maxSize={390} groupResizeBehavior='preserve-pixel-size'>{contextPanel}</ResizablePanel><ResizableHandle withHandle aria-label='Resize conversation list' />
      <ResizablePanel id='chat-conversation-v2' minSize={520}>{conversationPanel}</ResizablePanel><ResizableHandle withHandle aria-label='Resize execution timeline' />
      <ResizablePanel id='chat-timeline-v2' defaultSize={280} minSize={240} maxSize={420} collapsible collapsedSize={0} groupResizeBehavior='preserve-pixel-size'>{timelinePanel}</ResizablePanel>
    </ResizablePanelGroup> : <div className='min-h-0 flex-1 space-y-4 overflow-auto'><div className='min-h-[28rem] overflow-hidden rounded-md border'>{contextPanel}</div><div className='min-h-[42rem] overflow-hidden rounded-md border'>{conversationPanel}</div><div className='overflow-hidden rounded-md border'>{timelinePanel}</div></div>}
  </Main><WorkspaceDialog open={workspaceOpen} onOpenChange={setWorkspaceOpen} data={workspaceQuery.data} loading={workspaceQuery.isLoading} refreshing={refreshWorkspace.isPending} busyAction={previewWorkspaceFile.isPending || deleteWorkspaceFile.isPending || deleteMemory.isPending} onRefresh={() => refreshWorkspace.mutate()} onClearMemory={() => setClearMemoryOpen(true)}
    onPreview={(path) => previewWorkspaceFile.mutate(path)} onDownload={(path) => void downloadWorkspaceFile(path)}
    onDeleteFile={(path) => { if (window.confirm(`Delete workspace file "${path}"?`)) deleteWorkspaceFile.mutate(path) }}
    onDeleteMemory={(id) => { if (window.confirm('Delete this memory entry from the database and workspace?')) deleteMemory.mutate(id) }} />
    <ClearMemoryDialog open={clearMemoryOpen} onOpenChange={setClearMemoryOpen} systemCode={workspaceQuery.data?.system.code ?? ''} confirmation={clearMemoryConfirmation} onConfirmationChange={setClearMemoryConfirmation} busy={clearMemory.isPending} onConfirm={() => clearMemory.mutate()} />
    <WorkspacePreviewDialog preview={workspacePreview} onOpenChange={(open) => !open && setWorkspacePreview(undefined)} />
    <Dialog open={bypassWarningOpen} onOpenChange={setBypassWarningOpen}><DialogContent className='max-w-xl'>
      <DialogHeader><DialogTitle>Enable session-only Policy bypass?</DialogTitle>
        <DialogDescription>This grants the AI Agent permission to execute validated operations without Policy decisions or approval prompts for this conversation only.</DialogDescription></DialogHeader>
      <div className='rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm'>
        Command validation, writable-path restrictions, SSH Gateway timeouts, output limits and complete Audit logging remain mandatory. This setting does not apply to other conversations.
      </div>
      <DialogFooter><Button variant='outline' onClick={() => setBypassWarningOpen(false)}>Cancel</Button>
        <Button variant='destructive' disabled={changeBypass.isPending} onClick={() => changeBypass.mutate(true)}>Enable for this session</Button></DialogFooter>
    </DialogContent></Dialog>
    <CommandConsentDialog consent={commandConsent} busy={decideCommand.isPending} onDecision={submitCommandDecision} /></>
}

function CommandConsentDialog({ consent, busy, onDecision }: { consent?: { id: string; command: string; hostname?: string }; busy: boolean; onDecision: (decision: 'accept' | 'reject' | 'accept_session' | 'accept_command') => void }) {
  return <Dialog open={Boolean(consent)}><DialogContent showCloseButton={false} className='max-w-2xl'><DialogHeader><DialogTitle>AI-proposed SSH command</DialogTitle><DialogDescription>{consent?.hostname ? `Target: ${consent.hostname}. ` : ''}The current AI execution is paused here. Your decision is returned to the same Codex task, which then continues automatically.</DialogDescription></DialogHeader>
    <pre className='max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted/40 p-4 text-sm'>{consent?.command}</pre>
    <div className='flex flex-wrap justify-end gap-2'><Button variant='destructive' disabled={busy} onClick={() => onDecision('reject')}>Reject</Button><Button variant='outline' disabled={busy} onClick={() => onDecision('accept_command')}>Accept for this command</Button><Button variant='outline' disabled={busy} onClick={() => onDecision('accept_session')}>Accept all this session</Button><Button disabled={busy} onClick={() => onDecision('accept')}>Accept once</Button></div>
  </DialogContent></Dialog>
}

function WorkspaceDialog({ open, onOpenChange, data, loading, refreshing, busyAction, onRefresh, onClearMemory, onPreview, onDownload, onDeleteFile, onDeleteMemory }: { open: boolean; onOpenChange: (value: boolean) => void; data?: WorkspaceOverview; loading: boolean; refreshing: boolean; busyAction: boolean; onRefresh: () => void; onClearMemory: () => void; onPreview: (path: string) => void; onDownload: (path: string) => void; onDeleteFile: (path: string) => void; onDeleteMemory: (id: string) => void }) {
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className='max-h-[90vh] max-w-5xl overflow-hidden p-0'><DialogHeader className='border-b px-6 py-4'><div className='flex flex-wrap items-start justify-between gap-4 pe-8'><div><DialogTitle>System workspace & memory</DialogTitle><DialogDescription>{data ? `${data.system.code} - ${data.system.name}` : 'Loading the selected System context...'}</DialogDescription></div><div className='flex flex-wrap gap-2'><Button size='sm' variant='destructive' disabled={loading || !data} onClick={onClearMemory}><Eraser className='size-4' />Clear memory</Button><Button size='sm' variant='outline' disabled={loading || refreshing} onClick={onRefresh}><RefreshCw className={cn('size-4', refreshing && 'animate-spin')} />Refresh workspace</Button></div></div></DialogHeader>
    <div className='grid min-h-0 flex-1 gap-0 overflow-hidden md:grid-cols-2'>{loading ? <p className='col-span-2 p-8 text-center text-sm text-muted-foreground'>Loading workspace information...</p> : <><section className='min-h-0 border-r'><div className='border-b px-5 py-3'><p className='font-medium'>Workspace files <span className='text-muted-foreground'>({data?.file_count ?? 0})</span></p><p className='truncate text-xs text-muted-foreground' title={data?.workspace_path}>{data?.workspace_path}</p></div><div className='max-h-[62vh] overflow-auto p-3'>{(data?.files ?? []).map((file) => <div key={file.path} className='group flex items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-muted'><code className='min-w-0 flex-1 truncate' title={file.path}>{file.path}</code><span className='shrink-0 text-muted-foreground'>{formatBytes(file.size)}</span><div className='flex shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100'><Button title='Preview file' aria-label={`Preview ${file.path}`} size='icon' variant='ghost' className='size-7' disabled={busyAction} onClick={() => onPreview(file.path)}><Eye className='size-3.5' /></Button><Button title='Download file' aria-label={`Download ${file.path}`} size='icon' variant='ghost' className='size-7' disabled={busyAction} onClick={() => onDownload(file.path)}><Download className='size-3.5' /></Button>{file.deletable && <Button title='Delete file' aria-label={`Delete ${file.path}`} size='icon' variant='ghost' className='size-7 text-destructive' disabled={busyAction} onClick={() => onDeleteFile(file.path)}><Trash2 className='size-3.5' /></Button>}</div></div>)}</div></section>
      <section className='min-h-0'><div className='border-b px-5 py-3'><p className='font-medium'>Memory summaries <span className='text-muted-foreground'>({data?.memory_count ?? 0})</span></p><p className='text-xs text-muted-foreground'>Recent backend recovery memory; full history is not sent by default.</p></div><div className='max-h-[62vh] space-y-2 overflow-auto p-3'>{(data?.memories ?? []).map((memory) => <article key={memory.id} className='group rounded-md border p-3'><div className='flex items-start justify-between gap-2'><div className='min-w-0 flex-1'><p className='truncate text-sm font-medium'>{memory.topic}</p><span className='mt-1 inline-block rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground'>{memory.category}</span></div><Button title='Delete memory' aria-label={`Delete memory ${memory.topic}`} size='icon' variant='ghost' className='size-7 shrink-0 text-destructive opacity-0 group-hover:opacity-100 focus:opacity-100' disabled={busyAction} onClick={() => onDeleteMemory(memory.id)}><Trash2 className='size-3.5' /></Button></div><p className='mt-2 whitespace-pre-wrap break-words text-xs text-muted-foreground'>{memory.summary}</p></article>)}</div></section></>}</div>
  </DialogContent></Dialog>
}

function WorkspacePreviewDialog({ preview, onOpenChange }: { preview?: WorkspacePreview; onOpenChange: (open: boolean) => void }) {
  return <Dialog open={Boolean(preview)} onOpenChange={onOpenChange}><DialogContent className='grid max-h-[88svh] grid-rows-[auto_minmax(0,1fr)] overflow-hidden sm:max-w-4xl'><DialogHeader><DialogTitle className='break-all'>{preview?.path}</DialogTitle><DialogDescription>{preview ? `${formatBytes(preview.size)}${preview.truncated ? ' / preview truncated at 500 KB' : ''}` : ''}</DialogDescription></DialogHeader>
    <div className='min-h-0 overflow-auto rounded-md border bg-muted/30 p-4'>{preview?.previewable ? <pre className='whitespace-pre-wrap break-words text-xs leading-relaxed'>{preview.content}</pre> : <div className='grid min-h-48 place-items-center text-center text-sm text-muted-foreground'>This binary file cannot be previewed safely. Use Download to inspect the original file.</div>}</div></DialogContent></Dialog>
}

function ClearMemoryDialog({ open, onOpenChange, systemCode, confirmation, onConfirmationChange, busy, onConfirm }: { open: boolean; onOpenChange: (value: boolean) => void; systemCode: string; confirmation: string; onConfirmationChange: (value: string) => void; busy: boolean; onConfirm: () => void }) {
  const confirmed = Boolean(systemCode) && confirmation === systemCode
  return <Dialog open={open} onOpenChange={(value) => !busy && onOpenChange(value)}><DialogContent className='max-w-lg'><DialogHeader><DialogTitle>Clear System memory</DialogTitle><DialogDescription>This permanently removes learned memory from the database and workspace. Conversation history and source knowledge remain available, while the active Codex thread is reset.</DialogDescription></DialogHeader><div className='space-y-2'><label htmlFor='clear-memory-confirmation' className='text-sm font-medium'>Type <code className='rounded bg-muted px-1.5 py-0.5'>{systemCode}</code> to confirm</label><Input id='clear-memory-confirmation' autoComplete='off' value={confirmation} onChange={(event) => onConfirmationChange(event.target.value)} /></div><DialogFooter><Button variant='outline' disabled={busy} onClick={() => onOpenChange(false)}>Cancel</Button><Button variant='destructive' disabled={!confirmed || busy} onClick={onConfirm}>{busy ? 'Clearing...' : 'Clear memory'}</Button></DialogFooter></DialogContent></Dialog>
}

function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB` }

function Message({ role, text, createdAt, pending }: { role: string; text: string; createdAt?: string; pending?: boolean }) {
  const user = role === 'user' || role === 'You'
  return <div className={cn('flex gap-3', user && 'flex-row-reverse')}><Avatar className='mt-0.5 size-8'><AvatarFallback>{user ? 'Y' : <Bot className='size-4' />}</AvatarFallback></Avatar><div className={cn('max-w-[min(46rem,82%)]', user && 'text-right')}><div className={cn('inline-block rounded-md px-3 py-2 text-left text-sm', user ? 'bg-primary text-primary-foreground' : 'border bg-muted/50')}>
    {pending && !text ? <span className='flex items-center gap-2 text-muted-foreground'><span className='flex gap-1' aria-label='AI is answering'><span className='size-1.5 animate-bounce rounded-full bg-current [animation-delay:-.3s]' /><span className='size-1.5 animate-bounce rounded-full bg-current [animation-delay:-.15s]' /><span className='size-1.5 animate-bounce rounded-full bg-current' /></span>AI is answering</span> : <p className='whitespace-pre-wrap break-words'>{text}</p>}
  </div>{createdAt && <p className='mt-1 text-xs text-muted-foreground'>{new Date(createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>}</div></div>
}

function TimelineItem({ event, last }: { event: TimelineEvent; last: boolean }) {
  const Icon = event.state === 'failed' || event.state === 'attention' ? CircleAlert : event.state === 'complete' ? CheckCircle2 : Clock3
  return <div className='grid grid-cols-[20px_minmax(0,1fr)] gap-2'><div className='flex flex-col items-center'><Icon className={cn('size-4 shrink-0', event.state === 'running' && 'animate-pulse text-primary', event.state === 'complete' && 'text-emerald-500', event.state === 'attention' && 'text-amber-500', event.state === 'failed' && 'text-destructive')} />{!last && <span className='my-1 w-px flex-1 bg-border' />}</div><div className='min-w-0 pb-4'><div className='flex items-start justify-between gap-2'><p className='break-words text-sm font-medium'>{event.label}</p><time className='shrink-0 text-[11px] text-muted-foreground'>{event.occurredAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time></div>{event.detail && <p className='mt-1 max-h-24 overflow-auto break-words rounded bg-muted/50 p-2 font-mono text-[11px] text-muted-foreground'>{event.detail}</p>}</div></div>
}

function EmptySidebar({ text }: { text: string }) { return <div className='grid min-h-32 place-items-center px-4 text-center text-sm text-muted-foreground'>{text}</div> }
function formatRelative(value?: string) { if (!value) return 'No activity yet'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? 'No activity yet' : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) }

function ToolContract() { return <Sheet><SheetTrigger asChild><Button className='mt-auto w-full' variant='outline'><Wrench className='size-4' />View Tool Contract</Button></SheetTrigger><SheetContent><SheetHeader><SheetTitle>Tool Registry Contract</SheetTitle><SheetDescription>AI may propose only a read-only SSH command. The backend remains responsible for validation, policy, approval, execution and audit.</SheetDescription></SheetHeader><div className='space-y-3 px-4'><div className='rounded-md border p-3 text-sm'><div className='font-medium'>run_ssh_command</div><div className='text-muted-foreground'>Backend-controlled SSH command proposal</div></div></div></SheetContent></Sheet> }
