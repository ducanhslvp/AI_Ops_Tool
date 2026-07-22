import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from '@tanstack/react-router'
import { ArrowLeft, Bot, ExternalLink, Network, Server, TerminalSquare } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from './status-badge'

interface ServerDetail {
  id: string
  system_id: string
  environment_id: string
  hostname: string
  ip_address: string
  os: string
  server_type: string
  role: string
  description: string
  tags: string[]
  status: string
  ssh_config: { port?: number }
  updated_at: string
}

interface NamedResource { id: string; name: string; code?: string }
interface AuditEvent { id: string; tool_name?: string; result: string; decision?: string; created_at: string; duration_ms: number; provider?: string | null; ssh_command?: string | null; output_preview?: string; exit_code?: number | null; approval_used?: boolean }
interface KnowledgeItem { id: string; title: string; document_type: string; updated_at: string; graph_nodes: unknown[]; graph_edges: unknown[] }

export function ServerDetailRoute() {
  const { serverId } = useParams({
    from: '/_authenticated/inventory/servers/$serverId',
  })
  return <ServerDetailPage serverId={serverId} />
}

function ServerDetailPage({ serverId }: { serverId: string }) {
  const navigate = useNavigate()
  const serverQuery = useQuery({
    queryKey: ['inventory', 'server', serverId],
    queryFn: async () => (await apiClient.get<ServerDetail>(`/inventory/servers/${serverId}`)).data,
  })
  const server = serverQuery.data
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems', 'metadata'], queryFn: async () =>
    (await apiClient.get<NamedResource[]>('/inventory/systems', { params: { limit: 500 } })).data })
  const environmentsQuery = useQuery({ queryKey: ['inventory', 'environments'], queryFn: async () =>
    (await apiClient.get<NamedResource[]>('/inventory/environments')).data })
  const auditQuery = useQuery({
    queryKey: ['audit', 'server', serverId],
    queryFn: async () => (await apiClient.get<AuditEvent[]>('/audit', {
      params: { server_id: serverId, limit: 20 },
    })).data,
  })
  const knowledgeQuery = useQuery({
    queryKey: ['knowledge', 'system', server?.system_id],
    enabled: Boolean(server?.system_id),
    queryFn: async () => (await apiClient.get<KnowledgeItem[]>('/knowledge', {
      params: { system_id: server?.system_id, limit: 20 },
    })).data,
  })

  if (serverQuery.isPending) return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header>
    <Main><Skeleton className='h-8 w-72' /><Skeleton className='mt-6 h-80 w-full' /></Main></>
  if (serverQuery.isError || !server) return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header>
    <Main><div className='space-y-3'><h1 className='text-xl font-semibold'>Server unavailable</h1>
      <p className='text-sm text-muted-foreground'>The record could not be loaded or you no longer have access.</p>
      <Button variant='outline' onClick={() => serverQuery.refetch()}>Retry</Button></div></Main></>

  const system = systemsQuery.data?.find((item) => item.id === server.system_id)
  const environment = environmentsQuery.data?.find((item) => item.id === server.environment_id)
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <Button variant='ghost' size='sm' className='mb-3' onClick={() => navigate({ to: '/inventory' })}>
      <ArrowLeft className='size-4' />Inventory</Button>
    <div className='flex flex-wrap items-start justify-between gap-4'><div className='min-w-0'>
      <div className='flex items-center gap-3'><Server className='size-6 text-muted-foreground' />
        <h1 className='truncate text-2xl font-semibold'>{server.hostname}</h1><StatusBadge value={server.status} /></div>
      <p className='mt-1 text-sm text-muted-foreground'>{server.ip_address} - {server.os}</p></div>
      <div className='flex gap-2'><Button variant='outline' onClick={() => navigate({ to: '/chats' })}>
        <Bot className='size-4' />Ask AI</Button><Button onClick={() => navigate({ to: '/terminal' })}>
        <TerminalSquare className='size-4' />Open terminal</Button></div></div>
    <Tabs defaultValue='overview' className='mt-6'>
      <TabsList><TabsTrigger value='overview'>Overview</TabsTrigger><TabsTrigger value='audit'>Audit</TabsTrigger>
        <TabsTrigger value='knowledge'>Knowledge</TabsTrigger><TabsTrigger value='dependencies'>Dependencies</TabsTrigger></TabsList>
      <TabsContent value='overview' className='mt-4 grid gap-4 lg:grid-cols-3'>
        <Card className='lg:col-span-2'><CardHeader><CardTitle>Configuration</CardTitle>
          <CardDescription>Non-secret inventory metadata available to operators and AI tools.</CardDescription></CardHeader>
          <CardContent className='grid gap-4 sm:grid-cols-2'>
            <Detail label='System' value={system ? `${system.code ?? ''} ${system.name}`.trim() : server.system_id} />
            <Detail label='Environment' value={environment?.name ?? server.environment_id} />
            <Detail label='Type' value={server.server_type} /><Detail label='Role' value={server.role || 'Not assigned'} />
            <Detail label='SSH port' value={String(server.ssh_config.port ?? 22)} />
            <Detail label='Last updated' value={new Date(server.updated_at).toLocaleString()} />
          </CardContent></Card>
        <Card><CardHeader><CardTitle>Health</CardTitle></CardHeader><CardContent className='space-y-4'>
          <div className='flex items-center justify-between'><span className='text-sm text-muted-foreground'>Connectivity</span>
            <StatusBadge value={server.status} /></div><p className='text-sm text-muted-foreground'>{server.description || 'No operational notes recorded.'}</p>
          <div className='flex flex-wrap gap-2'>{server.tags.map((tag) => <span key={tag} className='rounded-sm border px-2 py-1 text-xs'>{tag}</span>)}</div>
        </CardContent></Card>
      </TabsContent>
      <TabsContent value='audit' className='mt-4'><Card><CardHeader><CardTitle>Recent Audit</CardTitle>
        <CardDescription>Immutable operations recorded for this server.</CardDescription></CardHeader><CardContent className='space-y-2'>
        {(auditQuery.data ?? []).map((event) => <div key={event.id} className='grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b py-3 last:border-0'>
          <div className='min-w-0'><p className='text-sm font-medium'>{event.tool_name ?? 'Platform event'}</p>
            <p className='text-xs text-muted-foreground'>{new Date(event.created_at).toLocaleString()} - {event.duration_ms} ms - exit {event.exit_code ?? '-'}</p>
            {event.ssh_command && <code className='mt-1 block truncate text-xs' title={event.ssh_command}>{event.ssh_command}</code>}
            {event.output_preview && <p className='mt-1 line-clamp-2 text-xs text-muted-foreground'>{event.output_preview}</p>}</div>
          <StatusBadge value={event.result} /></div>)}
        {!auditQuery.data?.length && <p className='py-8 text-center text-sm text-muted-foreground'>No audit activity recorded for this server.</p>}
      </CardContent></Card></TabsContent>
      <TabsContent value='knowledge' className='mt-4'><div className='grid gap-3 md:grid-cols-2'>
        {(knowledgeQuery.data ?? []).map((item) => <Card key={item.id}><CardHeader><CardTitle className='text-base'>{item.title}</CardTitle>
          <CardDescription>{item.document_type} - updated {new Date(item.updated_at).toLocaleDateString()}</CardDescription></CardHeader>
          <CardContent><Button variant='outline' size='sm' onClick={() => navigate({ to: '/knowledge' })}>
            Open knowledge <ExternalLink className='size-4' /></Button></CardContent></Card>)}
      </div></TabsContent>
      <TabsContent value='dependencies' className='mt-4'><Card><CardHeader><CardTitle>Dependency Context</CardTitle>
        <CardDescription>Graph evidence indexed from knowledge documents for this system.</CardDescription></CardHeader><CardContent>
        <div className='flex items-center gap-3'><Network className='size-5 text-muted-foreground' /><p className='text-sm'>
          {(knowledgeQuery.data ?? []).reduce((sum, item) => sum + item.graph_nodes.length, 0)} nodes and{' '}
          {(knowledgeQuery.data ?? []).reduce((sum, item) => sum + item.graph_edges.length, 0)} relationships indexed.</p></div>
      </CardContent></Card></TabsContent>
    </Tabs>
  </Main></>
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><p className='text-xs text-muted-foreground'>{label}</p><p className='mt-1 break-words text-sm font-medium'>{value}</p></div>
}
