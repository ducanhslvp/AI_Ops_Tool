import { useMemo, useState } from 'react'
import type { AxiosError } from 'axios'
import { useMutation, useQuery } from '@tanstack/react-query'
import { LoaderCircle, Play, ServerCog } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { SearchableSelect } from '@/components/searchable-select'
import { QueryLoadError } from '@/components/query-load-error'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { useIsMobile } from '@/hooks/use-mobile'
import { StatusBadge } from './status-badge'

interface SystemRecord { id: string; code: string; name: string }
interface ExecutionResult {
  server_id: string
  hostname: string
  ip_address: string
  status: string
  decision: string
  exit_code: number | null
  output: string
  duration_ms: number
  approval_id: string | null
}
interface ErrorBody { error?: { message?: string }; detail?: string }

export function TerminalPage() {
  const isMobile = useIsMobile()
  const [systemId, setSystemId] = useState('')
  const [command, setCommand] = useState('')
  const [workers, setWorkers] = useState(10)
  const systemsQuery = useQuery({
    queryKey: ['inventory', 'systems', 'multi-server-terminal'],
    queryFn: async () => (await apiClient.get<SystemRecord[]>('/inventory/systems', {
      params: { page: 1, page_size: 1000 },
    })).data,
  })
  const execute = useMutation({
    mutationFn: async () => (await apiClient.post<ExecutionResult[]>('/tools/execute-system', {
      system_id: systemId,
      command: command.trim(),
      workers,
      reason: `Human operator requested multi-server command: ${command.trim()}`,
    })).data,
  })
  const columns: EnterpriseColumn<ExecutionResult>[] = useMemo(() => [
    { id: 'server', header: 'Server', accessor: (item) => item.hostname,
      cell: (item) => <div><p className='font-medium'>{item.hostname}</p><p className='text-xs text-muted-foreground'>{item.ip_address}</p></div>, size: 180 },
    { id: 'status', header: 'Status', accessor: (item) => item.status,
      cell: (item) => <StatusBadge value={item.status} />, size: 110 },
    { id: 'exit', header: 'Exit code', accessor: (item) => item.exit_code ?? '', size: 80 },
    { id: 'duration', header: 'Duration', accessor: (item) => item.duration_ms,
      cell: (item) => `${item.duration_ms} ms`, size: 90 },
    { id: 'output', header: 'Output', accessor: (item) => item.output,
      cell: (item) => <pre className='max-h-40 min-w-72 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/50 p-3 font-mono text-xs'>{item.output || 'No output returned.'}</pre>, size: 420 },
  ], [])
  const error = execute.error as AxiosError<ErrorBody> | null
  const errorMessage = error?.response?.data?.error?.message ?? error?.response?.data?.detail

  return <>
    <Header><Search /><ThemeSwitch /><ProfileDropdown /></Header>
    <Main fixed>
      <div className='mb-4 flex flex-wrap items-start justify-between gap-3'>
        <div><h1 className='text-2xl font-semibold'>Multi-Server Terminal</h1>
          <p className='text-sm text-muted-foreground'>Execute one validated CLI command concurrently across every server in a System.</p></div>
      </div>
      <QueryLoadError visible={systemsQuery.isError} retrying={systemsQuery.isFetching}
        message='Systems could not be loaded.' onRetry={() => systemsQuery.refetch()} />
      <ResizablePanelGroup id='multi-server-terminal-v1' orientation={isMobile ? 'vertical' : 'horizontal'}
        className='min-h-0 flex-1 overflow-hidden rounded-md border'>
        <ResizablePanel id='terminal-controls' defaultSize={isMobile ? 330 : 340} minSize={isMobile ? 280 : 300}
          maxSize={isMobile ? 520 : 480} groupResizeBehavior='preserve-pixel-size'>
          <section className='flex h-full flex-col gap-4 overflow-auto p-4'>
            <div><h2 className='font-medium'>Execution target</h2>
              <p className='text-xs text-muted-foreground'>One command is validated independently for every server.</p></div>
            <div className='space-y-1.5'><Label>System</Label><SearchableSelect ariaLabel='Target System'
              value={systemId} searchPlaceholder='Search Systems...' placeholder='Select a System'
              options={(systemsQuery.data ?? []).map((item) => ({ value: item.id, label: `${item.code} - ${item.name}` }))}
              onValueChange={(value) => { setSystemId(value); execute.reset() }} /></div>
            <div className='space-y-1.5'><Label htmlFor='terminal-command'>CLI command</Label><Textarea id='terminal-command'
              className='min-h-28 resize-y font-mono' maxLength={512} value={command}
              placeholder='df -h' onChange={(event) => { setCommand(event.target.value); execute.reset() }} /></div>
            <div className='space-y-1.5'><Label htmlFor='terminal-workers'>Parallel workers</Label><Input id='terminal-workers'
              type='number' min={1} max={32} value={workers} onChange={(event) => setWorkers(Math.max(1, Math.min(32, Number(event.target.value) || 1)))} />
              <p className='text-xs text-muted-foreground'>Choose 1–32 concurrent SSH Gateway workers.</p></div>
            {errorMessage && <div className='rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive'>{errorMessage}</div>}
            <div className='mt-auto space-y-3'><div className='flex items-start gap-2 text-xs text-muted-foreground'>
              <ServerCog className='mt-0.5 size-4 shrink-0' />Policy, command validation, Gateway limits and Audit apply to every target.
            </div><Button className='w-full' disabled={!systemId || !command.trim() || execute.isPending}
              onClick={() => execute.mutate()}>{execute.isPending ? <LoaderCircle className='size-4 animate-spin' /> : <Play className='size-4' />}Execute on System</Button></div>
          </section>
        </ResizablePanel>
        <ResizableHandle withHandle aria-label='Resize terminal controls and results' />
        <ResizablePanel id='terminal-results' minSize={isMobile ? 360 : 520}>
          <section className='flex h-full min-h-0 flex-col p-4'>
            <div className='mb-3 flex items-center justify-between gap-3'><div><h2 className='font-medium'>Execution results</h2>
              <p className='text-xs text-muted-foreground'>Server-specific status, output and duration.</p></div>
              {execute.data && <div className='text-right text-xs'><p className='font-medium'>{execute.data.length} processed</p>
                <p className='text-muted-foreground'>{execute.data.filter((item) => item.status === 'success').length} successful</p></div>}
            </div>
            <div className='min-h-0 flex-1'><EnterpriseDataTable data={execute.data ?? []} columns={columns} getRowId={(item) => item.server_id}
              entityName='server result' searchPlaceholder='Search server, IP, status or output'
              loading={execute.isPending}
              emptyTitle='No execution results' emptyDescription='Select a System and run a validated command to see one result per server.' /></div>
          </section>
        </ResizablePanel>
      </ResizablePanelGroup>
    </Main>
  </>
}
