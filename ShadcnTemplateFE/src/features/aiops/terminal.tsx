import { useMemo, useState } from 'react'
import type { AxiosError } from 'axios'
import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle, Play, ShieldCheck, SquareTerminal } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { useIsDesktop } from '@/hooks/use-desktop'
import { Button } from '@/components/ui/button'
import { SearchableSelect } from '@/components/searchable-select'
import { QueryLoadError } from '@/components/query-load-error'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ServerTargetSelector, type TargetEnvironment, type TargetServer, type TargetSystem } from '@/components/server-target-selector'

interface ServerRecord extends TargetServer {
  server_type: string
  ssh_config: { test_profile?: string }
}

interface ToolRecord {
  name: string
  description: string
  risk_level: string
  target_types: string[]
  arguments_schema: Record<string, unknown>
}

interface ExecutionResult {
  action: string
  decision: string
  stdout: string | null
  stderr: string | null
  exit_code: number | null
  command_ref: string | null
  confidence: { score: number; reason: string; need_more_data: boolean }
}

interface ApiErrorBody {
  error?: { message?: string; approval_id?: string }
}

interface DevelopmentStatus {
  enabled: boolean
  transport: string
  profiles: Array<{ id: string; name: string; description: string }>
}

export function TerminalPage() {
  const isDesktop = useIsDesktop()
  const [serverId, setServerId] = useState('')
  const [action, setAction] = useState('')
  const serversQuery = useQuery({
    queryKey: ['inventory', 'servers'],
    queryFn: async () =>
      (await apiClient.get<ServerRecord[]>('/inventory/servers', { params: { page: 1, page_size: 200 } })).data,
  })
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems', 'target-selector'], queryFn: async () =>
    (await apiClient.get<TargetSystem[]>('/inventory/systems', { params: { page: 1, page_size: 200 } })).data })
  const environmentsQuery = useQuery({ queryKey: ['inventory', 'environments', 'target-selector'], queryFn: async () =>
    (await apiClient.get<TargetEnvironment[]>('/inventory/environments', { params: { page: 1, page_size: 200 } })).data })
  const toolsQuery = useQuery({
    queryKey: ['tools'],
    queryFn: async () => (await apiClient.get<ToolRecord[]>('/tools')).data,
  })
  const developmentQuery = useQuery({
    queryKey: ['development', 'status'],
    queryFn: async () =>
      (await apiClient.get<DevelopmentStatus>('/development/status')).data,
    retry: false,
    staleTime: 60_000,
  })
  const selectedServer = serversQuery.data?.find((item) => item.id === serverId)
  const availableTools = useMemo(() => {
    if (!selectedServer) return []
    const normalizedOs = selectedServer.os.toLowerCase().includes('win')
      ? 'windows'
      : 'linux'
    return (toolsQuery.data ?? []).filter(
      (tool) =>
        Object.keys(tool.arguments_schema).length === 0 &&
        (tool.target_types.includes(selectedServer.server_type.toLowerCase()) ||
          tool.target_types.includes(normalizedOs))
    )
  }, [selectedServer, toolsQuery.data])
  const execute = useMutation({
    mutationFn: async () =>
      (
        await apiClient.post<ExecutionResult>('/tools/execute', {
          server_id: serverId,
          action,
          arguments: {},
          reason: `Human operator requested ${action} from controlled action console`,
        })
      ).data,
  })
  const setProfile = useMutation({
    mutationFn: async (profile: string) =>
      (await apiClient.put(`/development/servers/${serverId}/profile`, { profile })).data,
    onSuccess: async () => {
      await serversQuery.refetch()
      execute.reset()
      toast.success('Development test profile updated.')
    },
    onError: () => toast.error('Test profile could not be updated.'),
  })
  const apiError = execute.error as AxiosError<ApiErrorBody> | null
  const approvalId = apiError?.response?.data?.error?.approval_id
  const errorMessage = apiError?.response?.data?.error?.message

  return (
    <>
      <Header>
        <Search />
        <ThemeSwitch />
        <ProfileDropdown />
      </Header>
      <Main fixed>
        <div className='mb-4'>
          <h1 className='text-2xl font-semibold tracking-tight'>
            Gateway Actions
          </h1>
          <p className='text-sm text-muted-foreground'>
            Human-initiated actions routed through policy, Tool Registry and the
            short-lived SSH Gateway.
          </p>
        </div>
        <QueryLoadError visible={serversQuery.isError || systemsQuery.isError || environmentsQuery.isError || toolsQuery.isError}
          retrying={serversQuery.isFetching || systemsQuery.isFetching || environmentsQuery.isFetching || toolsQuery.isFetching}
          message='Targets or registered actions could not be loaded. Your session is preserved.' onRetry={() => Promise.all([
            serversQuery.refetch(), systemsQuery.refetch(), environmentsQuery.refetch(), toolsQuery.refetch(),
          ])} />
        <ResizablePanelGroup
          id='terminal-workspace'
          orientation={isDesktop ? 'horizontal' : 'vertical'}
          className='min-h-0 flex-1 overflow-hidden rounded-md border'
        >
          <ResizablePanel
            id='terminal-targets'
            defaultSize={isDesktop ? 300 : 240}
            minSize={isDesktop ? 250 : 200}
            maxSize={isDesktop ? 440 : '55%'}
            groupResizeBehavior='preserve-pixel-size'
          >
          <Card className='flex h-full min-h-0 flex-col rounded-none border-0 shadow-none'>
            <CardHeader>
              <CardTitle className='text-base'>Targets</CardTitle>
            </CardHeader>
            <CardContent className='min-h-0 flex-1 space-y-2 overflow-auto'>
              <ServerTargetSelector layout='sidebar' systems={systemsQuery.data ?? []} environments={environmentsQuery.data ?? []}
                servers={serversQuery.data ?? []} value={serverId} onChange={(id) => { setServerId(id); setAction(''); execute.reset() }} />
              {serversQuery.isLoading && (
                <p className='text-sm text-muted-foreground'>
                  Loading targets...
                </p>
              )}
            </CardContent>
          </Card>
          </ResizablePanel>
          <ResizableHandle withHandle aria-label='Resize target panel' />
          <ResizablePanel id='terminal-console' minSize={isDesktop ? 480 : 320}>
          <Card className='flex h-full min-h-0 flex-col rounded-none border-0 shadow-none'>
            <CardHeader className='border-b'>
              <div className='flex flex-wrap items-center justify-between gap-3'>
                <CardTitle className='flex items-center gap-2 text-base'>
                  <SquareTerminal className='size-4' />
                  {selectedServer ? `${selectedServer.hostname} / ${selectedServer.ip_address}` : 'Select a target'}
                </CardTitle>
                {developmentQuery.data?.enabled && selectedServer && (
                  <label className='flex items-center gap-2 text-xs text-muted-foreground'>
                    Test profile
                    <SearchableSelect ariaLabel='Development test profile' value={selectedServer.ssh_config.test_profile ?? 'healthy'}
                      disabled={setProfile.isPending} onValueChange={(value) => setProfile.mutate(value)} className='h-8 min-w-48 text-xs'
                      searchPlaceholder='Search test profiles...' options={developmentQuery.data.profiles.map((profile) => ({ value: profile.id, label: profile.name, keywords: profile.description }))} />
                  </label>
                )}
              </div>
            </CardHeader>
            <CardContent className='flex min-h-0 flex-1 flex-col gap-4 p-4'>
              <div className='grid gap-2 sm:grid-cols-[1fr_auto]'>
                <SearchableSelect ariaLabel='Approved action' value={action} placeholder='Select an approved no-argument action'
                  searchPlaceholder='Search registered actions...' disabled={!selectedServer}
                  options={availableTools.map((tool) => ({ value: tool.name, label: `${tool.name} - ${tool.description}`, keywords: tool.risk_level }))}
                  onValueChange={(value) => { setAction(value); execute.reset() }} />
                <Button
                  disabled={!serverId || !action || execute.isPending}
                  onClick={() => execute.mutate()}
                >
                  {execute.isPending ? (
                    <LoaderCircle className='size-4 animate-spin' />
                  ) : (
                    <Play className='size-4' />
                  )}
                  Execute
                </Button>
              </div>
              <div className='min-h-0 flex-1 overflow-auto rounded-md bg-zinc-950 p-4 font-mono text-sm text-zinc-100'>
                {!execute.data && !execute.error && (
                  <p className='text-zinc-400'>
                    Select a target and registered action.
                  </p>
                )}
                {execute.data && (
                  <>
                    <p className='text-emerald-400'>
                      Decision: {execute.data.decision}
                    </p>
                    <p>Reference: {execute.data.command_ref}</p>
                    <pre className='mt-3 break-words whitespace-pre-wrap'>
                      {execute.data.stdout ||
                        execute.data.stderr ||
                        'No output returned.'}
                    </pre>
                    <p className='mt-3 text-zinc-400'>
                      Confidence:{' '}
                      {Math.round(execute.data.confidence.score * 100)}% -{' '}
                      {execute.data.confidence.reason}
                    </p>
                  </>
                )}
                {execute.error && (
                  <div className='space-y-2 text-amber-300'>
                    <p>{errorMessage ?? 'Controlled execution failed.'}</p>
                    {approvalId && (
                      <p className='flex items-center gap-2'>
                        <ShieldCheck className='size-4' /> Approval request:{' '}
                        {approvalId}
                      </p>
                    )}
                  </div>
                )}
              </div>
              <p className='text-xs text-muted-foreground'>
                Arbitrary shell input is unavailable. Actions with arguments are
                executed from AI Chat or dedicated workflows with validated
                forms.
              </p>
              {developmentQuery.data?.enabled && selectedServer && (
                <p className='text-xs text-muted-foreground'>
                  {developmentQuery.data.profiles.find((profile) =>
                    profile.id === (selectedServer.ssh_config.test_profile ?? 'healthy'))?.description}
                </p>
              )}
            </CardContent>
          </Card>
          </ResizablePanel>
        </ResizablePanelGroup>
      </Main>
    </>
  )
}
