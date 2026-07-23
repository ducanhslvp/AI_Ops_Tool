import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, useNodesState, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Boxes, CalendarClock, ChevronDown, ChevronRight, Network, Play, Power, PowerOff, RotateCw, SearchCode, Trash2, Waypoints } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SearchableSelect } from '@/components/searchable-select'
import { ThemeSwitch } from '@/components/theme-switch'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import type { TargetEnvironment, TargetServer, TargetSystem } from '@/components/server-target-selector'
import { StatusBadge } from './status-badge'

type SystemRecord = TargetSystem
type EnvironmentRecord = TargetEnvironment
type ServerRecord = TargetServer
interface InfraData extends Record<string, unknown> { hostname: string; ip: string; os: string; server_type: string; role: string; health: string;
  system_id: string; system: string; environment: string; cpu_cores?: number; ram_bytes?: number; disk_count?: number; disk_total_bytes?: number;
  docker?: boolean; kubernetes?: boolean; services?: string[]; listening_ports?: Array<{ port: number; protocol?: string; service: string }>;
  containers?: Array<Record<string, string>>; kubernetes_resources?: Array<Record<string, string>>; filesystems?: Array<Record<string, string>>;
  interfaces?: string[]; open_ports?: Array<{ port: number; protocol?: string; service: string }>; installed_applications?: string[];
  docker_networks?: Array<Record<string, string>>; docker_compose?: Array<Record<string, string>>; pods?: Array<Record<string, string>> }
interface InfraNode { id: string; type: string; data: InfraData }
interface InfraEdge { id: string; source: string; target: string; port: number; protocol: string; connection_type: string;
  service_name: string; confidence: number; reason: string }
interface Scan { id: string; system_id: string | null; status: string; summary: string; nodes: InfraNode[]; edges: InfraEdge[];
  change_summary: Record<string, string[] | boolean>; completed_at: string | null; created_at: string }
interface Schedule { id: string; name: string; system_id: string | null; server_ids: string[]; interval_minutes: number; incremental: boolean;
  include_system_services: boolean; enabled: boolean; next_run_at: string | null }
type GroupMode = 'system' | 'environment' | 'network' | 'docker' | 'kubernetes'
type FlowNode = Node<InfraData, 'infra'>
interface GroupData extends Record<string, unknown> { group: string; count: number; collapsed: boolean }
type GroupFlowNode = Node<GroupData, 'infraGroup'>

const nodeTypes = { infra: InfrastructureNode, infraGroup: InfrastructureGroup }

export function DiscoveryPage() {
  const client = useQueryClient(); const navigate = useNavigate(); const [systemId, setSystemId] = useState(''); const [scan, setScan] = useState<Scan>()
  const [scopeMode, setScopeMode] = useState<'system' | 'servers'>('system'); const [selectedServerIds, setSelectedServerIds] = useState<string[]>([]); const [targetDialog, setTargetDialog] = useState(false)
  const [query, setQuery] = useState(''); const [environment, setEnvironment] = useState(''); const [showHealthy, setShowHealthy] = useState(true)
  const [includeSystem, setIncludeSystem] = useState(false); const [selectedNode, setSelectedNode] = useState<InfraNode>(); const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [groupMode, setGroupMode] = useState<GroupMode>('environment')
  const [scheduleDialog, setScheduleDialog] = useState(false)
  const [scheduleManager, setScheduleManager] = useState(false)
  const systems = useQuery({ queryKey: ['inventory', 'systems', 'discovery'], queryFn: async () => (await apiClient.get<SystemRecord[]>('/inventory/systems', { params: { page: 1, page_size: 200 } })).data })
  const servers = useQuery({ queryKey: ['inventory', 'servers', 'discovery'], queryFn: async () => (await apiClient.get<ServerRecord[]>('/inventory/servers', { params: { page: 1, page_size: 200 } })).data })
  const inventoryEnvironments = useQuery({ queryKey: ['inventory', 'environments', 'discovery'], queryFn: async () => (await apiClient.get<EnvironmentRecord[]>('/inventory/environments', { params: { page: 1, page_size: 200 } })).data })
  const scans = useQuery({ queryKey: ['discovery', 'scans'], queryFn: async () => (await apiClient.get<Scan[]>('/discovery/scans', { params: { page: 1, page_size: 50 } })).data })
  const schedules = useQuery({ queryKey: ['discovery', 'schedules'], queryFn: async () => (await apiClient.get<Schedule[]>('/discovery/schedules')).data })
  const current = scan ?? scans.data?.[0]
  const activeSystem = systemId || current?.system_id || systems.data?.[0]?.id || ''
  const canRun = scopeMode === 'system' ? Boolean(activeSystem) : selectedServerIds.length > 0
  const run = useMutation({ mutationFn: async () => (await apiClient.post<Scan>('/discovery/scans', { system_id: scopeMode === 'system' ? activeSystem : null, server_ids: scopeMode === 'servers' ? selectedServerIds : [], options: { include_system_services: includeSystem, incremental: true, namespace: 'default' } })).data,
    onSuccess: async (result) => { setScan(result); await client.invalidateQueries({ queryKey: ['discovery'] }); toast.success('Infrastructure snapshot and knowledge graph updated.') },
    onError: () => toast.error('Discovery did not complete. Review policy and gateway evidence.') })
  const runSchedule = useMutation({ mutationFn: async (item: Schedule) => (await apiClient.post<Scan>(`/discovery/schedules/${item.id}/run`)).data,
    onSuccess: async (result) => { setScan(result); await client.invalidateQueries({ queryKey: ['discovery'] }); toast.success('Scheduled discovery completed.') }, onError: () => toast.error('Scheduled discovery failed.') })
  const setScheduleStatus = useMutation({ mutationFn: async ({ item, enabled }: { item: Schedule; enabled: boolean }) => apiClient.put(`/discovery/schedules/${item.id}`, {
    name: item.name, system_id: item.system_id, server_ids: item.server_ids, interval_minutes: item.interval_minutes, incremental: item.incremental,
    include_system_services: item.include_system_services, enabled }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['discovery', 'schedules'] }); toast.success('Schedule status updated.') } })
  const deleteSchedules = useMutation({ mutationFn: async (items: Schedule[]) => Promise.all(items.map((item) => apiClient.delete(`/discovery/schedules/${item.id}`))),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['discovery', 'schedules'] }); toast.success('Selected schedules deleted.') }, onError: () => toast.error('Schedules could not be deleted.') })
  const environments = [...new Set((current?.nodes ?? []).map((node) => node.data.environment))]
  const visibleNodes = useMemo(() => (current?.nodes ?? []).filter((node) => {
    const text = JSON.stringify(node.data).toLowerCase(); return text.includes(query.toLowerCase()) && (!environment || node.data.environment === environment) && (showHealthy || node.data.health !== 'online')
  }), [current?.nodes, environment, query, showHealthy])
  const graph = useMemo(() => buildGraph(visibleNodes, current?.edges ?? [], collapsed, groupMode), [collapsed, current?.edges, groupMode, visibleNodes])
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([])
  const layoutKey = `aiops:discovery-layout:${current?.id ?? 'empty'}:${groupMode}:v2`
  useEffect(() => {
    const saved = readNodePositions(layoutKey)
    setFlowNodes(graph.nodes.map((node) => saved[node.id] ? { ...node, position: saved[node.id] } : node))
  }, [graph.nodes, layoutKey, setFlowNodes])
  const persistPosition = (movedNode: Node) => setFlowNodes((nodes) => {
    const next = nodes.map((node) => node.id === movedNode.id ? { ...node, position: movedNode.position } : node)
    writeNodePositions(layoutKey, next)
    return next
  })
  const toggleGroup = (group: string) => setCollapsed((value) => { const next = new Set(value); if (next.has(group)) next.delete(group); else next.add(group); return next })
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main className='max-w-none'>
    <div className='mb-4 flex flex-wrap items-start justify-between gap-3'><div><h1 className='flex items-center gap-2 text-2xl font-semibold'><Waypoints className='size-5' />Infrastructure Discovery</h1>
      <p className='text-sm text-muted-foreground'>Evidence-driven infrastructure topology through governed backend tools.</p></div><div className='flex gap-2'>
      <Button size='sm' variant='outline' onClick={() => setScheduleManager(true)}><CalendarClock className='size-4' />Scheduled scans ({schedules.data?.length ?? 0})</Button>
      <Button size='sm' disabled={!canRun || run.isPending} onClick={() => run.mutate()}><Play className='size-4' />{run.isPending ? 'Collecting and analyzing...' : 'Run discovery with AI'}</Button></div></div>
    <div className='mb-4 grid gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-4'><Metric label='Servers' value={current?.nodes.length ?? 0} /><Metric label='Dependencies' value={current?.edges.length ?? 0} />
      <Metric label='Containers' value={(current?.nodes ?? []).reduce((sum, node) => sum + (node.data.containers?.length ?? 0), 0)} /><Metric label='Changes' value={changeCount(current)} /></div>
    <div className='mb-3 flex flex-wrap items-center gap-2'><div className='flex h-9 rounded-md border p-0.5'><Button size='sm' variant={scopeMode === 'system' ? 'secondary' : 'ghost'} onClick={() => setScopeMode('system')}>System</Button><Button size='sm' variant={scopeMode === 'servers' ? 'secondary' : 'ghost'} onClick={() => setScopeMode('servers')}>Servers</Button></div>
      {scopeMode === 'system' ? <SearchableSelect ariaLabel='Discovery system' value={activeSystem} className='w-64' searchPlaceholder='Search systems...'
        options={(systems.data ?? []).map((system) => ({ value: system.id, label: `${system.code} - ${system.name}` }))}
        onValueChange={(id) => { setSystemId(id); setScan(scans.data?.find((item) => item.system_id === id)) }} /> : <Button variant='outline' onClick={() => setTargetDialog(true)}>{selectedServerIds.length || 'No'} servers selected</Button>}
      <SearchableSelect ariaLabel='Discovery snapshot' value={current?.id ?? ''} className='w-72' placeholder='Select snapshot' searchPlaceholder='Search snapshots...'
        options={(scans.data ?? []).map((item) => ({ value: item.id, label: `${new Date(item.created_at).toLocaleString()} - ${item.status}`, keywords: item.summary }))}
        onValueChange={(id) => setScan(scans.data?.find((item) => item.id === id))} />
      <div className='relative min-w-56 flex-1'><SearchCode className='absolute start-2 top-2.5 size-4 text-muted-foreground' /><Input className='ps-8' value={query} onChange={(e) => setQuery(e.target.value)} placeholder='Search loaded topology' /></div>
      <SearchableSelect ariaLabel='Discovery environment' value={environment} allowClear placeholder='All environments' className='w-48'
        options={environments.map((value) => ({ value, label: value }))} onValueChange={setEnvironment} />
      <select aria-label='Group topology by' value={groupMode} onChange={(e) => { setGroupMode(e.target.value as GroupMode); setCollapsed(new Set()) }} className='h-9 rounded-md border bg-background px-3 text-sm'><option value='system'>Group: System</option><option value='environment'>Group: Environment</option><option value='network'>Group: Network</option><option value='docker'>Group: Docker</option><option value='kubernetes'>Group: Kubernetes</option></select>
      <label className='flex items-center gap-2 text-sm'><Switch checked={showHealthy} onCheckedChange={setShowHealthy} />Healthy</label>
      <label className='flex items-center gap-2 text-sm'><Switch checked={includeSystem} onCheckedChange={setIncludeSystem} />System services</label></div>
    <div className='relative h-[min(68svh,760px)] min-h-[520px] overflow-hidden rounded-md border bg-muted/10'>
      {current ? <ReactFlow nodes={flowNodes} edges={graph.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.18 }} minZoom={0.15} maxZoom={2}
        onNodesChange={onNodesChange} onNodeDragStop={(_, node) => persistPosition(node)} nodesDraggable panOnDrag selectionOnDrag
        onNodeClick={(_, node) => { if (node.type === 'infraGroup') toggleGroup(String(node.data.group)); else setSelectedNode({ id: node.id, type: 'infra', data: node.data as InfraData }) }}>
        <Background gap={28} size={1} />
        <MiniMap pannable zoomable maskColor='color-mix(in oklch, var(--background) 72%, transparent)' bgColor='var(--background)' nodeStrokeWidth={3}
          className='!overflow-hidden !rounded-md !border !border-border !bg-background !shadow-sm' nodeColor={(node) => node.type === 'infraGroup' ? '#64748b' : healthColor(String(node.data.health))} />
        <Controls showInteractive className='!overflow-hidden !rounded-md !border !border-border !bg-background !shadow-sm [&>button]:!border-border [&>button]:!bg-background [&>button]:!fill-foreground [&>button:hover]:!bg-muted' />
      </ReactFlow> :
        <div className='grid h-full place-items-center text-sm text-muted-foreground'>Run discovery to create the first infrastructure snapshot.</div>}
    </div>
    {current && <div className='mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground'><p>{current.summary}</p><p>{current.completed_at ? new Date(current.completed_at).toLocaleString() : current.status}</p></div>}
    <Dialog open={scheduleManager} onOpenChange={setScheduleManager}><DialogContent className='grid max-h-[90svh] grid-rows-[auto_minmax(0,1fr)] overflow-hidden p-0 sm:max-w-6xl'><DialogHeader className='border-b px-6 py-5 pe-14'><div className='flex flex-wrap items-start justify-between gap-3'><div><DialogTitle>Scheduled discovery scans</DialogTitle><DialogDescription>Manage incremental and full topology scans without leaving the active diagram.</DialogDescription></div><Button size='sm' onClick={() => setScheduleDialog(true)}><CalendarClock className='size-4' />New schedule</Button></div></DialogHeader><div className='min-h-0 overflow-auto p-5'>
      <EnterpriseDataTable data={schedules.data ?? []} columns={scheduleColumns} getRowId={(item) => item.id} entityName='schedule' loading={schedules.isLoading} searchPlaceholder='Search loaded schedules'
        rowActions={[{ label: 'Run now', icon: RotateCw, onSelect: (item) => runSchedule.mutate(item) }, { label: 'Enable', icon: Power, hidden: (item) => item.enabled, onSelect: (item) => setScheduleStatus.mutate({ item, enabled: true }) },
          { label: 'Disable', icon: PowerOff, hidden: (item) => !item.enabled, onSelect: (item) => setScheduleStatus.mutate({ item, enabled: false }) }, { label: 'Delete', icon: Trash2, destructive: true, onSelect: (item) => deleteSchedules.mutate([item]) }]}
        bulkActions={[{ label: 'Delete selected', icon: Trash2, destructive: true, onSelect: (items) => deleteSchedules.mutate(items) }]} /></div></DialogContent></Dialog>
    <ScheduleDialog open={scheduleDialog} onOpenChange={setScheduleDialog} systems={systems.data ?? []} defaultSystemId={activeSystem} />
    <TargetDialog open={targetDialog} onOpenChange={setTargetDialog} systems={systems.data ?? []} environments={inventoryEnvironments.data ?? []}
      servers={servers.data ?? []} selected={selectedServerIds} onSelected={setSelectedServerIds} />
    <NodeDetailsDialog node={selectedNode} onOpenChange={(open) => !open && setSelectedNode(undefined)}
      onOpenInventory={(serverId) => void navigate({ to: '/inventory/servers/$serverId', params: { serverId } })} />
  </Main></>
}

function TargetDialog({ open, onOpenChange, systems, environments, servers, selected, onSelected }: { open: boolean; onOpenChange: (open: boolean) => void;
  systems: SystemRecord[]; environments: EnvironmentRecord[]; servers: ServerRecord[]; selected: string[]; onSelected: (value: string[]) => void }) {
  const [systemId, setSystemId] = useState(''); const [environmentId, setEnvironmentId] = useState('')
  const environmentIds = new Set(servers.filter((server) => server.system_id === systemId).map((server) => server.environment_id))
  const visibleServers = servers.filter((server) => server.system_id === systemId && (!environmentId || server.environment_id === environmentId))
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Select discovery targets</DialogTitle><DialogDescription>Select up to 50 servers. Policy is evaluated independently for every target and tool.</DialogDescription></DialogHeader>
    <div className='grid gap-2 sm:grid-cols-2'><SearchableSelect ariaLabel='Target system' value={systemId} placeholder='Select system' searchPlaceholder='Search systems...'
      options={systems.map((system) => ({ value: system.id, label: `${system.code} - ${system.name}` }))} onValueChange={(value) => { setSystemId(value); setEnvironmentId('') }} />
      <SearchableSelect ariaLabel='Target environment' value={environmentId} allowClear disabled={!systemId} placeholder='All system environments' searchPlaceholder='Search environments...'
        options={environments.filter((item) => environmentIds.has(item.id)).map((item) => ({ value: item.id, label: item.name }))} onValueChange={setEnvironmentId} /></div>
    <div className='max-h-96 divide-y overflow-auto rounded-md border'>{visibleServers.map((server) => <label key={server.id} className='flex items-center gap-3 p-3 text-sm'><Checkbox checked={selected.includes(server.id)} onCheckedChange={(checked) => onSelected(checked ? [...new Set([...selected, server.id])].slice(0, 50) : selected.filter((id) => id !== server.id))} />
      <span className='min-w-0 flex-1'><span className='block font-medium'>{server.hostname}</span><span className='text-xs text-muted-foreground'>{server.ip_address} / {server.os} / {server.role}</span></span><StatusBadge value={server.status} /></label>)}
      {!systemId && <p className='p-8 text-center text-sm text-muted-foreground'>Select a System before choosing servers.</p>}{systemId && !visibleServers.length && <p className='p-8 text-center text-sm text-muted-foreground'>No servers match this System and Environment.</p>}</div>
    <DialogFooter><Button onClick={() => onOpenChange(false)}>Done</Button></DialogFooter></DialogContent></Dialog>
}

function Metric({ label, value }: { label: string; value: number }) { return <div className='bg-background p-3'><p className='text-xs text-muted-foreground'>{label}</p><p className='mt-1 text-xl font-semibold tabular-nums'>{value}</p></div> }

const scheduleColumns: EnterpriseColumn<Schedule>[] = [
  { id: 'name', header: 'Name', accessor: (item) => item.name, cell: (item) => <span className='font-medium'>{item.name}</span>, size: 280 },
  { id: 'interval', header: 'Interval', accessor: (item) => item.interval_minutes, cell: (item) => `${item.interval_minutes} min`, size: 120 },
  { id: 'mode', header: 'Mode', accessor: (item) => item.incremental ? 'Incremental' : 'Full' },
  { id: 'next', header: 'Next run', accessor: (item) => item.next_run_at ?? '', cell: (item) => item.next_run_at ? new Date(item.next_run_at).toLocaleString() : 'Not scheduled', size: 190 },
  { id: 'status', header: 'Status', accessor: (item) => item.enabled ? 'active' : 'inactive', cell: (item) => <StatusBadge value={item.enabled ? 'active' : 'inactive'} /> },
]

function InfrastructureNode({ data, selected }: NodeProps<FlowNode>) {
  const [tooltipOpen, setTooltipOpen] = useState(false)
  return <Tooltip delayDuration={180} open={tooltipOpen} onOpenChange={setTooltipOpen}>
  <TooltipTrigger asChild><div onClick={() => setTooltipOpen(false)} className={`w-64 cursor-grab rounded-md border bg-background p-3 shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing ${selected ? 'ring-2 ring-primary' : ''}`}>
    <Handle type='target' position={Position.Left} /><div className='flex items-start justify-between gap-2'><div className='min-w-0'><p className='truncate text-sm font-semibold'>{data.hostname}</p><p className='truncate font-mono text-xs text-muted-foreground'>{data.ip}</p></div><span className='mt-1 size-2 rounded-full' style={{ background: healthColor(data.health) }} /></div>
    <p className='mt-2 truncate text-xs text-muted-foreground'>{data.os}</p><div className='mt-3 grid grid-cols-3 gap-1 text-center text-[11px]'><Signal label='CPU' value={data.cpu_cores ? `${data.cpu_cores} cores` : 'N/A'} /><Signal label='RAM' value={formatBytes(data.ram_bytes)} /><Signal label='Disk' value={diskSummary(data)} /></div>
    <div className='mt-2 flex min-h-4 items-center gap-2 truncate text-xs text-muted-foreground'>{data.docker && <Boxes className='size-3.5 shrink-0' />}{data.kubernetes && <Network className='size-3.5 shrink-0' />}{data.services?.slice(0, 2).join(', ') || 'No deployed service detected'}</div><Handle type='source' position={Position.Right} />
  </div></TooltipTrigger>
  <TooltipContent side='right' align='start' sideOffset={12} className='w-80 space-y-3 p-4'>
    <div className='flex items-start justify-between gap-3'><div className='min-w-0'><p className='break-all font-semibold'>{data.hostname}</p><p className='font-mono text-xs text-muted-foreground'>{data.ip}</p></div><StatusBadge value={data.health} /></div>
    <div className='grid grid-cols-2 gap-x-4 gap-y-2 text-xs'>
      <TooltipField label='OS' value={data.os} /><TooltipField label='CPU' value={data.cpu_cores ? `${data.cpu_cores} cores` : 'N/A'} />
      <TooltipField label='RAM' value={formatBytes(data.ram_bytes)} /><TooltipField label='Disk' value={diskSummary(data)} />
      <TooltipField label='Docker' value={data.docker ? `${data.containers?.length ?? 0} containers` : 'Not detected'} />
      <TooltipField label='Kubernetes' value={data.kubernetes ? `${data.kubernetes_resources?.length ?? 0} resources` : 'Not detected'} />
    </div>
    <div><p className='text-xs font-medium'>Primary services</p><p className='mt-1 text-xs leading-relaxed text-muted-foreground'>{data.services?.slice(0, 6).join(', ') || 'No deployed service detected'}</p></div>
    <p className='border-t pt-2 text-[11px] text-muted-foreground'>Click to inspect complete discovery details.</p>
  </TooltipContent>
</Tooltip>
}
function InfrastructureGroup({ data }: NodeProps<GroupFlowNode>) { return <div className='flex h-10 items-center gap-2 px-3 text-sm font-semibold text-muted-foreground'>
  {data.collapsed ? <ChevronRight className='size-4' /> : <ChevronDown className='size-4' />}<span>{data.group}</span><span className='font-normal'>({data.count})</span></div> }
function Signal({ label, value }: { label: string; value: string }) { return <div className='rounded border bg-muted/30 px-1 py-1'><span className='block text-muted-foreground'>{label}</span><span className='font-medium'>{value}</span></div> }

function NodeDetailsDialog({ node, onOpenChange, onOpenInventory }: { node?: InfraNode; onOpenChange: (open: boolean) => void; onOpenInventory: (serverId: string) => void }) {
  if (!node) return null
  const data = node.data
  return <Dialog open onOpenChange={onOpenChange}>
    <DialogContent className='grid max-h-[92svh] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 sm:max-w-5xl'>
      <DialogHeader className='border-b px-6 py-5 pe-14'>
        <div className='flex flex-wrap items-start justify-between gap-3'><div className='min-w-0'><DialogTitle className='break-all text-xl'>{data.hostname}</DialogTitle>
          <DialogDescription className='mt-1 font-mono'>{data.ip} | {data.os}</DialogDescription></div><StatusBadge value={data.health} /></div>
      </DialogHeader>
      <Tabs defaultValue='overview' className='flex min-h-0 flex-col px-6 pt-4'>
        <TabsList className='w-full justify-start overflow-x-auto'>
          <TabsTrigger value='overview'>Overview</TabsTrigger><TabsTrigger value='network'>Network</TabsTrigger>
          <TabsTrigger value='runtime'>Runtime</TabsTrigger><TabsTrigger value='evidence'>Complete evidence</TabsTrigger>
        </TabsList>
        <TabsContent value='overview' className='min-h-0 flex-1 overflow-y-auto py-5'>
          <DetailSection title='Identity and placement'>
            <DetailGrid fields={[
              ['Server ID', node.id], ['Hostname', data.hostname], ['IP address', data.ip], ['Health', data.health],
              ['Operating system', data.os], ['Server type', data.server_type], ['Role', data.role], ['System', data.system], ['Environment', data.environment],
            ]} />
          </DetailSection>
          <DetailSection title='Capacity'>
            <DetailGrid fields={[
              ['CPU', data.cpu_cores ? `${data.cpu_cores} cores` : 'Not detected'], ['RAM', formatBytes(data.ram_bytes)],
              ['Disk', diskSummary(data)], ['Physical disks', String(data.disk_count ?? 0)], ['Disk capacity', formatBytes(data.disk_total_bytes)],
            ]} />
          </DetailSection>
          <DetailSection title='Deployed services and applications'>
            <TagList values={[...(data.services ?? []), ...(data.installed_applications ?? [])]} empty='No deployed service or application detected.' />
          </DetailSection>
          <DataCollection title='Filesystems' items={data.filesystems} />
        </TabsContent>
        <TabsContent value='network' className='min-h-0 flex-1 overflow-y-auto py-5'>
          <DetailSection title='Network interfaces'>
            <TagList values={data.interfaces ?? []} empty='No network interface evidence returned.' monospace />
          </DetailSection>
          <DataCollection title='Listening ports' items={data.listening_ports} />
          <DataCollection title='Open ports' items={data.open_ports} />
        </TabsContent>
        <TabsContent value='runtime' className='min-h-0 flex-1 overflow-y-auto py-5'>
          <DetailSection title='Runtime status'>
            <DetailGrid fields={[
              ['Docker', data.docker ? 'Detected' : 'Not detected'], ['Containers', String(data.containers?.length ?? 0)],
              ['Kubernetes', data.kubernetes ? 'Detected' : 'Not detected'], ['Kubernetes resources', String(data.kubernetes_resources?.length ?? 0)],
            ]} />
          </DetailSection>
          <DataCollection title='Containers' items={data.containers} />
          <DataCollection title='Docker networks' items={data.docker_networks} />
          <DataCollection title='Docker Compose projects' items={data.docker_compose} />
          <DataCollection title='Kubernetes resources' items={data.kubernetes_resources} />
          <DataCollection title='Pods' items={data.pods} />
        </TabsContent>
        <TabsContent value='evidence' className='min-h-0 flex-1 overflow-y-auto py-5'>
          <p className='mb-3 text-sm text-muted-foreground'>Complete normalized discovery payload captured for this node. Secret values are never part of discovery evidence.</p>
          <pre className='overflow-x-auto rounded-md border bg-muted/30 p-4 text-xs leading-relaxed'>{JSON.stringify(data, null, 2)}</pre>
        </TabsContent>
      </Tabs>
      <DialogFooter className='border-t px-6 py-4'>
        <Button variant='outline' onClick={() => onOpenChange(false)}>Close</Button>
        <Button onClick={() => onOpenInventory(node.id)}>Open inventory record</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className='border-b py-4 first:pt-0 last:border-b-0'><h3 className='mb-3 text-sm font-semibold'>{title}</h3>{children}</section>
}

function DetailGrid({ fields }: { fields: Array<[string, string]> }) {
  return <dl className='grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3'>{fields.map(([label, value]) => <div key={label} className='min-w-0'>
    <dt className='text-xs text-muted-foreground'>{label}</dt><dd className='mt-1 break-words text-sm font-medium'>{value || 'Not detected'}</dd>
  </div>)}</dl>
}

function TagList({ values, empty, monospace = false }: { values: string[]; empty: string; monospace?: boolean }) {
  const unique = [...new Set(values.filter(Boolean))]
  if (!unique.length) return <p className='text-sm text-muted-foreground'>{empty}</p>
  return <div className='flex flex-wrap gap-2'>{unique.map((value) => <span key={value} className={`rounded-md border bg-muted/30 px-2 py-1 text-xs ${monospace ? 'font-mono' : ''}`}>{value}</span>)}</div>
}

function DataCollection({ title, items }: { title: string; items?: Array<Record<string, unknown>> }) {
  if (!items?.length) return <DetailSection title={title}><p className='text-sm text-muted-foreground'>No evidence detected.</p></DetailSection>
  return <DetailSection title={`${title} (${items.length})`}><div className='divide-y rounded-md border'>{items.map((item, index) => <dl key={`${title}-${index}`} className='grid gap-x-5 gap-y-2 p-3 sm:grid-cols-2 lg:grid-cols-3'>
    {Object.entries(item).map(([key, value]) => <div key={key} className='min-w-0'><dt className='text-[11px] text-muted-foreground'>{formatFieldName(key)}</dt>
      <dd className='mt-0.5 break-words text-xs font-medium'>{formatDetailValue(value)}</dd></div>)}
  </dl>)}</div></DetailSection>
}

function formatFieldName(value: string) { return value.replace(/_/g, ' ').replace(/\b\w/g, (character: string) => character.toUpperCase()) }
function formatDetailValue(value: unknown) { if (value === null || value === undefined || value === '') return 'Not detected'; if (typeof value === 'object') return JSON.stringify(value); return String(value) }

function buildGraph(items: InfraNode[], dependencies: InfraEdge[], collapsed: Set<string>, groupMode: GroupMode) {
  const groups = new Map<string, InfraNode[]>(); for (const item of items) { const key = groupKey(item, groupMode); groups.set(key, [...(groups.get(key) ?? []), item]) }
  const groupByNode = new Map(items.map((item) => [item.id, groupKey(item, groupMode)]))
  const groupDepth = calculateGroupDepths([...groups.keys()], dependencies, groupByNode)
  const columns = new Map<number, Array<[string, InfraNode[]]>>()
  for (const entry of groups.entries()) { const depth = groupDepth.get(entry[0]) ?? 0; columns.set(depth, [...(columns.get(depth) ?? []), entry]) }
  const nodes: Node[] = []
  for (const [depth, entries] of [...columns.entries()].sort(([left], [right]) => left - right)) {
    let columnY = 0
    for (const [group, unorderedChildren] of entries.sort(([left], [right]) => left.localeCompare(right))) {
      const children = orderNodesByDependency(unorderedChildren, dependencies)
      const groupId = `group-${groupMode}-${group.replace(/[^A-Za-z0-9]/g, '-')}`; const isCollapsed = collapsed.has(group)
      const height = isCollapsed ? 54 : Math.max(290, Math.ceil(children.length / 2) * 220 + 82)
      nodes.push({ id: groupId, type: 'infraGroup', position: { x: depth * 900, y: columnY }, draggable: true,
        style: { width: 820, height, background: 'rgba(100,116,139,.045)', border: '1px solid rgba(100,116,139,.32)', borderRadius: 6 }, data: { group, count: children.length, collapsed: isCollapsed } })
      if (!isCollapsed) children.forEach((item, index) => nodes.push({ id: item.id, type: 'infra', parentId: groupId, extent: 'parent', draggable: true,
        position: { x: 28 + (index % 2) * 390, y: 68 + Math.floor(index / 2) * 220 }, data: item.data }))
      columnY += height + 130
    }
  }
  const ids = new Set(nodes.map((node) => node.id)); const edges: Edge[] = dependencies.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, type: 'smoothstep',
    label: `${edge.service_name} / ${edge.protocol}:${edge.port}`, markerEnd: { type: MarkerType.ArrowClosed },
    pathOptions: { borderRadius: 18, offset: 28 }, interactionWidth: 28,
    style: { stroke: '#64748b', strokeWidth: 1.8, opacity: 0.92 }, labelShowBg: false,
    labelStyle: { fill: 'var(--foreground)', stroke: 'var(--background)', strokeWidth: 3, paintOrder: 'stroke', fontSize: 11, fontWeight: 600 } }))
  return { nodes, edges }
}

function calculateGroupDepths(groupNames: string[], dependencies: InfraEdge[], groupByNode: Map<string, string>) {
  const depths = new Map(groupNames.map((group) => [group, 0])); const maxPasses = Math.max(groupNames.length - 1, 1)
  for (let pass = 0; pass < maxPasses; pass += 1) { let changed = false
    for (const edge of dependencies) { const source = groupByNode.get(edge.source); const target = groupByNode.get(edge.target); if (!source || !target || source === target) continue
      const next = Math.min((depths.get(source) ?? 0) + 1, maxPasses); if (next > (depths.get(target) ?? 0)) { depths.set(target, next); changed = true } }
    if (!changed) break
  }
  return depths
}

function orderNodesByDependency(nodes: InfraNode[], dependencies: InfraEdge[]) {
  const ids = new Set(nodes.map((node) => node.id)); const score = new Map(nodes.map((node) => [node.id, 0]))
  for (const edge of dependencies) { if (ids.has(edge.source)) score.set(edge.source, (score.get(edge.source) ?? 0) - 1); if (ids.has(edge.target)) score.set(edge.target, (score.get(edge.target) ?? 0) + 1) }
  return [...nodes].sort((left, right) => (score.get(left.id) ?? 0) - (score.get(right.id) ?? 0) || left.data.hostname.localeCompare(right.data.hostname))
}

function groupKey(item: InfraNode, mode: GroupMode) { if (mode === 'system') return `System / ${item.data.system}`; if (mode === 'environment') return `${item.data.system} / ${item.data.environment}`
  if (mode === 'network') return `Network / ${item.data.ip.split('.').slice(0, 3).join('.')}.0/24`; if (mode === 'docker') return item.data.docker ? 'Docker hosts' : 'Non-Docker hosts'
  return item.data.kubernetes ? 'Kubernetes nodes' : 'Non-Kubernetes hosts' }

function ScheduleDialog({ open, onOpenChange, systems, defaultSystemId }: { open: boolean; onOpenChange: (open: boolean) => void; systems: SystemRecord[]; defaultSystemId: string }) {
  const client = useQueryClient(); const [name, setName] = useState('Daily infrastructure discovery'); const [systemId, setSystemId] = useState(defaultSystemId); const [interval, setInterval] = useState(1440); const [incremental, setIncremental] = useState(true)
  const save = useMutation({ mutationFn: async () => apiClient.post('/discovery/schedules', { name, system_id: systemId || defaultSystemId, server_ids: [], interval_minutes: interval, incremental, include_system_services: false, enabled: true }), onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ['discovery', 'schedules'] }); onOpenChange(false); toast.success('Discovery schedule created.') }, onError: () => toast.error('Schedule could not be created.') })
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Schedule discovery</DialogTitle><DialogDescription>Incremental scans persist only detected topology changes.</DialogDescription></DialogHeader><form id='schedule-form' className='space-y-3' onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
    <div className='space-y-1'><Label>Name</Label><Input required value={name} onChange={(e) => setName(e.target.value)} /></div><div className='space-y-1'><Label>System</Label><SearchableSelect ariaLabel='Schedule system' value={systemId || defaultSystemId} searchPlaceholder='Search systems...'
      options={systems.map((item) => ({ value: item.id, label: `${item.code} - ${item.name}` }))} onValueChange={setSystemId} /></div>
    <div className='space-y-1'><Label>Interval minutes</Label><Input type='number' min={15} max={525600} value={interval} onChange={(e) => setInterval(Number(e.target.value))} /></div><label className='flex items-center gap-2 text-sm'><Switch checked={incremental} onCheckedChange={setIncremental} />Incremental discovery</label></form>
    <DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='schedule-form' type='submit' disabled={save.isPending}>Create schedule</Button></DialogFooter></DialogContent></Dialog>
}
function formatBytes(value?: number) { if (!value) return 'N/A'; const units = ['B', 'KB', 'MB', 'GB', 'TB']; const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index > 2 ? 1 : 0)} ${units[index]}` }
function diskSummary(data: InfraData) { const filesystem = data.filesystems?.find((item) => item.use_percent || item.usage || item.used_percent)
  const usage = filesystem?.use_percent ?? filesystem?.usage ?? filesystem?.used_percent
  return usage ? String(usage) : `${data.disk_count ?? 0} / ${formatBytes(data.disk_total_bytes)}` }
function TooltipField({ label, value }: { label: string; value: string }) { return <div className='min-w-0'><p className='text-muted-foreground'>{label}</p><p className='mt-0.5 break-words font-medium text-foreground'>{value}</p></div> }
function readNodePositions(key: string): Record<string, { x: number; y: number }> { try { return JSON.parse(sessionStorage.getItem(key) ?? '{}') as Record<string, { x: number; y: number }> } catch { return {} } }
function writeNodePositions(key: string, nodes: Node[]) { try { sessionStorage.setItem(key, JSON.stringify(Object.fromEntries(nodes.map((node) => [node.id, node.position])))) } catch { /* Session storage can be unavailable in hardened browser contexts. */ } }
function healthColor(value: string) { return value === 'online' ? '#10b981' : value === 'degraded' ? '#f59e0b' : '#ef4444' }
function changeCount(scan?: Scan) { if (!scan) return 0; return Object.entries(scan.change_summary).reduce((sum, [key, value]) => key === 'baseline' || !Array.isArray(value) ? sum : sum + value.length, 0) }
