import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Activity, Bot, BrainCircuit, Download, FilePlus2, HardDrive,
  Plug, Radar, RefreshCw, Server, ShieldCheck, TerminalSquare, TriangleAlert } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { TopNav } from '@/components/layout/top-nav'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from '@/features/aiops/status-badge'

interface DashboardData {
  metrics: { system_health: number; systems: number; servers: number; online_servers: number;
    degraded_servers: number; offline_servers: number; open_alerts: number;
    critical_alerts: number; warning_alerts: number; ai_messages: number }
  components: { ai_providers: number; enabled_plugins: number; total_plugins: number;
    ssh_gateways: number; knowledge_documents: number }
  environments: Array<{ name: string; servers: number; online: number; health: number }>
  recommendations: Array<{ severity: string; title: string; reason: string; action_url: string }>
  trend: Array<{ time: string; operations: number; failures: number; latency_ms: number }>
  alerts: Array<{ id: string; title: string; severity: string; server_id: string | null; created_at: string }>
  recent_audit: Array<{ id: string; tool: string | null; server_id: string | null; user_id: string | null;
    decision: string | null; created_at: string }>
  systems: Array<{ id: string; code: string; name: string; owner: string; criticality: string;
    servers: number; health: number }>
  graph: Array<{ system_id: string; title: string; nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>> }>
  ai_activity: Array<{ id: string; title: string; provider: string; updated_at: string }>
}

export function Dashboard() {
  const navigate = useNavigate()
  const dashboard = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await apiClient.get<DashboardData>('/dashboard')).data,
    refetchInterval: 30_000,
  })
  const exportReport = useMutation({
    mutationFn: async () => (await apiClient.post<{ id: string }>('/reports', {
      title: `Platform health ${new Date().toLocaleDateString()}`, format: 'markdown', system_id: null,
    })).data,
    onSuccess: async ({ id }) => {
      const response = await apiClient.get(`/reports/${id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `platform-health-${id}.md`
      link.click()
      URL.revokeObjectURL(url)
      toast.success('Live platform report exported.')
    },
    onError: () => toast.error('Report export failed.'),
  })
  const data = dashboard.data
  return (
    <>
      <Header><TopNav links={topNav} className='me-auto' /><Search /><ThemeSwitch />
        <ConfigDrawer /><ProfileDropdown /></Header>
      <Main>
        <div className='mb-4 flex flex-wrap items-center justify-between gap-3'>
          <div><h1 className='text-2xl font-semibold tracking-tight'>AI Infrastructure Operations</h1>
            <p className='text-sm text-muted-foreground'>Live inventory, policy and audit evidence.</p></div>
          <div className='flex gap-2'>
            <Button title='Refresh dashboard' size='icon' variant='outline'
              disabled={dashboard.isFetching} onClick={() => dashboard.refetch()}>
              <RefreshCw className={`size-4 ${dashboard.isFetching ? 'animate-spin' : ''}`} />
            </Button>
            <Button size='sm' disabled={!data || exportReport.isPending} onClick={() => exportReport.mutate()}>
              <Download className='size-4' />Export report</Button>
          </div>
        </div>
        {dashboard.isError && <p className='text-sm text-destructive'>Dashboard data could not be loaded.</p>}
        {dashboard.isPending ? <DashboardSkeleton /> : <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-6'>
          <MetricCard icon={Radar} label='System health' value={`${data?.metrics.system_health ?? 0}%`}
            detail={`${data?.metrics.systems ?? 0} systems tracked`} />
          <MetricCard icon={Server} label='Online servers'
            value={`${data?.metrics.online_servers ?? 0}/${data?.metrics.servers ?? 0}`}
            detail={`${data?.metrics.degraded_servers ?? 0} degraded`} />
          <MetricCard icon={TriangleAlert} label='Open alerts' value={String(data?.metrics.open_alerts ?? 0)}
            detail={`${data?.metrics.critical_alerts ?? 0} critical`} />
          <MetricCard icon={HardDrive} label='Offline servers' value={String(data?.metrics.offline_servers ?? 0)}
            detail={`${data?.metrics.degraded_servers ?? 0} degraded`} />
          <MetricCard icon={Bot} label='AI messages' value={String(data?.metrics.ai_messages ?? 0)}
            detail='Persisted session activity' />
          <MetricCard icon={Plug} label='Active plugins' value={`${data?.components?.enabled_plugins ?? 0}/${data?.components?.total_plugins ?? 0}`}
            detail={`${data?.components?.ai_providers ?? 0} AI provider active`} />
        </div>}
        <div className='mt-4 grid gap-4 border-y py-4 lg:grid-cols-[1fr_auto]'>
          <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-4'>
            <ComponentStatus label='AI provider' value={data?.components?.ai_providers ?? 0} />
            <ComponentStatus label='SSH gateway' value={data?.components?.ssh_gateways ?? 0} />
            <ComponentStatus label='Plugins' value={data?.components?.enabled_plugins ?? 0} />
            <ComponentStatus label='Knowledge' value={data?.components?.knowledge_documents ?? 0} neutral />
          </div>
          <div className='flex flex-wrap items-center gap-2'>
            <Button size='sm' variant='outline' onClick={() => navigate({ to: '/chats' })}>
              <BrainCircuit className='size-4' />Analyze health</Button>
            <Button size='sm' variant='outline' onClick={() => navigate({ to: '/terminal' })}>
              <TerminalSquare className='size-4' />Open terminal</Button>
            <Button size='sm' variant='outline' onClick={() => navigate({ to: '/reports' })}>
              <FilePlus2 className='size-4' />New report</Button>
          </div>
        </div>
        <Tabs defaultValue='overview' className='mt-4 space-y-4'>
          <TabsList><TabsTrigger value='overview'>Overview</TabsTrigger>
            <TabsTrigger value='systems'>Systems</TabsTrigger><TabsTrigger value='knowledge'>Graph</TabsTrigger></TabsList>
          <TabsContent value='overview' className='space-y-4'>
            <div className='grid gap-4 xl:grid-cols-7'>
              <Card className='xl:col-span-4'><CardHeader><CardTitle>Operations Trend</CardTitle>
                <CardDescription>Audited operations and failures over seven days.</CardDescription></CardHeader>
                <CardContent className='h-[310px]'><ResponsiveContainer width='100%' height='100%'>
                  <AreaChart data={data?.trend ?? []}><CartesianGrid strokeDasharray='3 3' className='stroke-muted' />
                    <XAxis dataKey='time' className='text-xs' /><YAxis className='text-xs' />
                    <Tooltip contentStyle={{ background: 'var(--background)', border: '1px solid var(--border)' }} />
                    <Area type='monotone' dataKey='operations' stroke='#22c55e' fill='#22c55e33' strokeWidth={2} />
                    <Area type='monotone' dataKey='failures' stroke='#ef4444' fill='#ef444422' strokeWidth={2} />
                  </AreaChart></ResponsiveContainer></CardContent></Card>
              <Card className='xl:col-span-3'><CardHeader><CardTitle>Top Alerts</CardTitle>
                <CardDescription>Open alerts from the database.</CardDescription></CardHeader>
                <CardContent className='space-y-3'>{(data?.alerts ?? []).map((alert) => (
                  <div key={alert.id} className='rounded-md border p-3'><div className='flex justify-between gap-3'>
                    <div className='min-w-0'><p className='truncate text-sm font-medium'>{alert.title}</p>
                      <p className='text-xs text-muted-foreground'>{alert.server_id?.slice(0, 8) ?? 'Platform'} · {new Date(alert.created_at).toLocaleString()}</p></div>
                    <StatusBadge value={alert.severity} /></div></div>))}</CardContent></Card>
            </div>
            <div className='grid gap-4 xl:grid-cols-2'>
              <Card><CardHeader><CardTitle>Recent Audit</CardTitle></CardHeader><CardContent className='space-y-3'>
                {(data?.recent_audit ?? []).map((event) => <div key={event.id}
                  className='grid grid-cols-[100px_1fr_auto] items-center gap-3 rounded-md border p-3'>
                  <span className='text-xs text-muted-foreground'>{new Date(event.created_at).toLocaleTimeString()}</span>
                  <div className='min-w-0'><p className='truncate text-sm font-medium'>{event.tool ?? 'system event'}</p>
                    <p className='truncate text-xs text-muted-foreground'>{event.server_id?.slice(0, 8) ?? 'Platform'}</p></div>
                  <StatusBadge value={event.decision ?? 'recorded'} /></div>)}</CardContent></Card>
              <Card><CardHeader><CardTitle>AI Activity</CardTitle></CardHeader><CardContent className='space-y-3'>
                {(data?.ai_activity ?? []).map((item) => <div key={item.id} className='rounded-md border p-3'>
                  <div className='flex items-center justify-between'><span className='text-sm font-medium'>{item.title}</span>
                    <StatusBadge value={item.provider} /></div><p className='mt-1 text-xs text-muted-foreground'>
                    {new Date(item.updated_at).toLocaleString()}</p></div>)}</CardContent></Card>
            </div>
            <div className='grid gap-4 xl:grid-cols-2'>
              <Card><CardHeader><CardTitle>Environment Health</CardTitle>
                <CardDescription>Current availability by operating environment.</CardDescription></CardHeader>
                <CardContent className='space-y-4'>{(data?.environments ?? []).map((environment) => (
                  <div key={environment.name} className='space-y-2'><div className='flex items-center justify-between text-sm'>
                    <span className='font-medium'>{environment.name}</span>
                    <span className='text-muted-foreground'>{environment.online}/{environment.servers} online</span></div>
                    <div className='h-2 overflow-hidden rounded-full bg-muted'><div className='h-full bg-primary'
                      style={{ width: `${environment.health}%` }} /></div></div>))}</CardContent></Card>
              <Card><CardHeader><CardTitle>Recommendations</CardTitle>
                <CardDescription>Prioritized from current platform state.</CardDescription></CardHeader>
                <CardContent className='space-y-3'>{(data?.recommendations ?? []).map((item) => (
                  <button key={item.title} className='flex w-full items-start justify-between gap-3 rounded-md border p-3 text-left hover:bg-accent'
                    onClick={() => navigate({ to: item.action_url })}>
                    <span><span className='block text-sm font-medium'>{item.title}</span>
                      <span className='mt-1 block text-xs text-muted-foreground'>{item.reason}</span></span>
                    <StatusBadge value={item.severity} />
                  </button>))}
                  {!data?.recommendations?.length && <p className='py-6 text-center text-sm text-muted-foreground'>No immediate action is recommended.</p>}
                </CardContent></Card>
            </div>
          </TabsContent>
          <TabsContent value='systems'><div className='grid gap-3 lg:grid-cols-3'>{(data?.systems ?? []).map((system) => (
            <Card key={system.id}><CardHeader><div className='flex justify-between gap-2'><div><CardTitle>{system.code}</CardTitle>
              <CardDescription>{system.name}</CardDescription></div><StatusBadge value={system.criticality} /></div></CardHeader>
              <CardContent className='space-y-3'><p className='flex items-center gap-2 text-sm'><ShieldCheck className='size-4' />{system.owner}</p>
                <p className='text-sm'>{system.servers} servers · {system.health}% online</p>
                <div className='h-2 rounded-full bg-muted'><div className='h-2 rounded-full bg-primary' style={{ width: `${system.health}%` }} /></div>
              </CardContent></Card>))}</div></TabsContent>
          <TabsContent value='knowledge'><Card><CardHeader><CardTitle>Knowledge Graph</CardTitle></CardHeader>
            <CardContent className='grid gap-3 md:grid-cols-2'>{(data?.graph ?? []).map((graph) => <div key={`${graph.system_id}-${graph.title}`}
              className='rounded-md border p-4'><p className='font-medium'>{graph.title}</p><p className='mt-2 flex items-center gap-2 text-sm text-muted-foreground'>
                <Activity className='size-4' />{graph.nodes.length} nodes · {graph.edges.length} edges</p></div>)}</CardContent></Card></TabsContent>
        </Tabs>
      </Main>
    </>
  )
}

function MetricCard({ icon: Icon, label, value, detail }: { icon: React.ElementType; label: string; value: string; detail: string }) {
  return <Card><CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
    <CardTitle className='text-sm font-medium'>{label}</CardTitle><Icon className='size-4 text-muted-foreground' /></CardHeader>
    <CardContent><div className='text-2xl font-semibold'>{value}</div><p className='text-xs text-muted-foreground'>{detail}</p></CardContent></Card>
}

function ComponentStatus({ label, value, neutral = false }: { label: string; value: number; neutral?: boolean }) {
  const healthy = neutral || value > 0
  return <div className='flex items-center gap-2 text-sm'><span aria-hidden className={`size-2 rounded-full ${healthy ? 'bg-emerald-500' : 'bg-amber-500'}`} />
    <span className='text-muted-foreground'>{label}</span><span className='font-medium'>{value}</span></div>
}

function DashboardSkeleton() {
  return <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-6' aria-label='Loading dashboard'>
    {Array.from({ length: 6 }, (_, index) => <Card key={index}><CardContent className='space-y-3 p-5'>
      <Skeleton className='h-4 w-24' /><Skeleton className='h-8 w-16' /><Skeleton className='h-3 w-32' />
    </CardContent></Card>)}
  </div>
}

const topNav = [{ title: 'Overview', href: '/', isActive: true }, { title: 'Inventory', href: '/inventory', isActive: false },
  { title: 'AI Chat', href: '/chats', isActive: false }, { title: 'Audit', href: '/audit', isActive: false }]
