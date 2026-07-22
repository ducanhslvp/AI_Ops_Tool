import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Download, Eye, GitCompare, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SearchableSelect } from '@/components/searchable-select'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { StatusBadge } from './status-badge'

interface SystemRecord { id: string; code: string; name: string }
interface MemoryRecord { id: string; category: string; topic: string; summary: string; source_type: string; occurred_at: string; archived_at: string | null }
interface SessionStatus { provider: string; status: string; connected: boolean; last_activity: string | null; workspace_path: string; context_size: number; memory_size: number; active_conversations: number }
type Operation = 'reset-conversations' | 'reset-memory' | 'refresh-memory' | 'refresh-knowledge' | 'rebuild-workspace' | 'archive-memory'

const operations: { value: Operation; label: string; description: string; destructive?: boolean }[] = [
  { value: 'refresh-memory', label: 'Refresh memory', description: 'Rebuild learned memory from retained conversations.' },
  { value: 'refresh-knowledge', label: 'Refresh knowledge', description: 'Regenerate document, discovery, and inventory projections.' },
  { value: 'rebuild-workspace', label: 'Rebuild workspace', description: 'Recreate generated files without deleting source uploads.' },
  { value: 'archive-memory', label: 'Archive memory', description: 'Move active memory out of the default AI context.' },
  { value: 'reset-conversations', label: 'Reset conversations', description: 'Delete chat history while preserving memory and knowledge.', destructive: true },
  { value: 'reset-memory', label: 'Reset memory', description: 'Delete learned memory while preserving conversations and knowledge.', destructive: true },
]

export function MemoryPage() {
  const client = useQueryClient()
  const [systemId, setSystemId] = useState('')
  const [category, setCategory] = useState('')
  const [archived, setArchived] = useState(false)
  const [view, setView] = useState<MemoryRecord>()
  const [comparison, setComparison] = useState<string>()
  const [operation, setOperation] = useState<Operation>()
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems'], queryFn: async () =>
    (await apiClient.get<SystemRecord[]>('/inventory/systems')).data })
  const memoriesQuery = useQuery({ queryKey: ['ai-memory', systemId, category, archived], enabled: Boolean(systemId), queryFn: async () =>
    (await apiClient.get<MemoryRecord[]>(`/ai/systems/${systemId}/memories`, { params: { page: 1, page_size: 200, category: category || undefined, archived } })).data })
  const statusQuery = useQuery({ queryKey: ['ai-session-status', systemId], enabled: Boolean(systemId), refetchInterval: 15_000, queryFn: async () =>
    (await apiClient.get<SessionStatus>(`/ai/systems/${systemId}/session-status`)).data })
  const systems = systemsQuery.data ?? []
  const selectedSystem = systems.find((item) => item.id === systemId)
  const columns = useMemo<EnterpriseColumn<MemoryRecord>[]>(() => [
    { id: 'topic', header: 'Topic', accessor: (item) => item.topic, cell: (item) => <div className='min-w-0'><p className='truncate font-medium'>{item.topic}</p><p className='truncate text-xs text-muted-foreground'>{item.summary}</p></div>, size: 420 },
    { id: 'category', header: 'Category', accessor: (item) => item.category, cell: (item) => <StatusBadge value={item.category} />, size: 140 },
    { id: 'source', header: 'Source', accessor: (item) => item.source_type, size: 130 },
    { id: 'occurred', header: 'Occurred', accessor: (item) => item.occurred_at, cell: (item) => new Date(item.occurred_at).toLocaleString(), size: 190 },
    { id: 'actions', header: 'Actions', accessor: (item) => item.id, enableHiding: false, size: 64, cell: (item) => <div className='flex justify-end'><Button size='icon' variant='ghost' title='View memory' aria-label={`View ${item.topic}`} onClick={() => setView(item)}><Eye className='size-4' /></Button></div> },
  ], [])
  const compare = useMutation({ mutationFn: async (items: MemoryRecord[]) => (await apiClient.post<{ diff: string }>(`/ai/systems/${systemId}/memories/compare`, { left_id: items[0].id, right_id: items[1].id })).data,
    onSuccess: (data) => setComparison(data.diff || 'No summary changes.'), onError: () => toast.error('Select exactly two memory records to compare.') })
  const exportMemory = async () => { if (!systemId) return; const { data } = await apiClient.get<{ filename: string; markdown: string }>(`/ai/systems/${systemId}/memories/export`)
    const url = URL.createObjectURL(new Blob([data.markdown], { type: 'text/markdown' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = data.filename; anchor.click(); URL.revokeObjectURL(url) }
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4 flex flex-wrap items-end justify-between gap-3'><div><h1 className='text-2xl font-semibold'>AI Memory</h1><p className='text-sm text-muted-foreground'>Persistent, system-scoped operational memory managed by the backend.</p></div>
      <div className='flex flex-wrap gap-2'><Button variant='outline' disabled={!systemId} onClick={() => void exportMemory()}><Download className='size-4' />Export</Button>
        <Button variant='outline' disabled={!systemId} onClick={() => setOperation('refresh-memory')}><RefreshCw className='size-4' />Maintain</Button></div></div>
    <div className='mb-4 grid gap-3 lg:grid-cols-[minmax(280px,420px)_1fr]'><div><Label className='mb-1.5 block'>System</Label><SearchableSelect ariaLabel='Memory system' value={systemId} placeholder='Select a system' searchPlaceholder='Search systems...'
      options={systems.map((item) => ({ value: item.id, label: `${item.code} - ${item.name}` }))} onValueChange={setSystemId} /></div>
      {statusQuery.data && <div className='grid grid-cols-2 gap-x-6 gap-y-2 border-l pl-4 text-sm md:grid-cols-4'><Metric label='Session' value={statusQuery.data.status} /><Metric label='Provider' value={statusQuery.data.provider} /><Metric label='Context' value={formatBytes(statusQuery.data.context_size)} /><Metric label='Memory' value={formatBytes(statusQuery.data.memory_size)} /><p className='col-span-full truncate text-xs text-muted-foreground' title={statusQuery.data.workspace_path}>{statusQuery.data.connected ? 'Connected' : 'Disconnected'} / {statusQuery.data.active_conversations} conversation(s) / {statusQuery.data.workspace_path}</p></div>}
    </div>
    <Card><CardContent className='pt-6'><EnterpriseDataTable data={memoriesQuery.data ?? []} columns={columns} getRowId={(item) => item.id} loading={memoriesQuery.isLoading}
      entityName='memory record' searchPlaceholder='Search topic or summary' emptyTitle={systemId ? 'No memory records' : 'Select a system'} emptyDescription={systemId ? 'Run a system-scoped AI conversation to create memory.' : 'Memory is isolated by System.'}
      filterSlot={<div className='flex gap-2'><SearchableSelect ariaLabel='Memory category' value={category} allowClear placeholder='All categories' className='w-44' options={['daily', 'incidents', 'operations', 'summaries', 'decisions'].map((value) => ({ value, label: value }))} onValueChange={setCategory} />
        <Button variant={archived ? 'secondary' : 'outline'} size='sm' onClick={() => setArchived((value) => !value)}><Archive className='size-4' />Archived</Button></div>}
      bulkActions={[{ label: 'Compare selected', icon: GitCompare, onSelect: (items) => { if (items.length === 2) compare.mutate(items); else toast.error('Select exactly two records.') } }]} /></CardContent></Card>
    <Dialog open={Boolean(view)} onOpenChange={(open) => !open && setView(undefined)}><DialogContent className='max-h-[80svh] max-w-3xl overflow-auto'><DialogHeader><DialogTitle>{view?.topic}</DialogTitle><DialogDescription>{view?.category} / {view && new Date(view.occurred_at).toLocaleString()}</DialogDescription></DialogHeader><p className='whitespace-pre-wrap text-sm'>{view?.summary}</p></DialogContent></Dialog>
    <Dialog open={Boolean(comparison)} onOpenChange={(open) => !open && setComparison(undefined)}><DialogContent className='max-h-[80svh] max-w-4xl overflow-auto'><DialogHeader><DialogTitle>Memory comparison</DialogTitle><DialogDescription>Unified summary diff</DialogDescription></DialogHeader><pre className='whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-xs'>{comparison}</pre></DialogContent></Dialog>
    <MaintenanceDialog operation={operation} system={selectedSystem} onSelect={setOperation} onOpenChange={(open) => !open && setOperation(undefined)} onDone={async () => { await client.invalidateQueries({ queryKey: ['ai-memory', systemId] }); await client.invalidateQueries({ queryKey: ['ai-session-status', systemId] }) }} />
  </Main></>
}

function Metric({ label, value }: { label: string; value: string }) { return <div><p className='text-xs text-muted-foreground'>{label}</p><p className='truncate font-medium'>{value}</p></div> }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB` }

function MaintenanceDialog({ operation, system, onSelect, onOpenChange, onDone }: { operation?: Operation; system?: SystemRecord; onSelect: (operation: Operation) => void; onOpenChange: (open: boolean) => void; onDone: () => Promise<void> }) {
  const [confirmation, setConfirmation] = useState('')
  const definition = operations.find((item) => item.value === operation)
  const mutation = useMutation({ mutationFn: async () => apiClient.post(`/ai/systems/${system?.id}/${operation}`, { confirm_system_code: confirmation }), onSuccess: async () => { await onDone(); toast.success(`${definition?.label} completed.`); setConfirmation(''); onOpenChange(false) }, onError: () => toast.error('Maintenance operation failed.') })
  return <Dialog open={Boolean(operation)} onOpenChange={onOpenChange}><DialogContent className='max-w-2xl'><DialogHeader><DialogTitle>{definition?.label}</DialogTitle><DialogDescription>{definition?.description}</DialogDescription></DialogHeader>
    <div className='grid gap-3 sm:grid-cols-2'>{operations.map((item) => <Button key={item.value} variant={item.value === operation ? 'secondary' : 'outline'} className='h-auto justify-start py-3 text-left' onClick={() => { setConfirmation(''); onSelect(item.value) }}><span><span className='block font-medium'>{item.label}</span><span className='block text-xs font-normal text-muted-foreground'>{item.description}</span></span></Button>)}</div>
    <div className='space-y-1.5'><Label>Type {system?.code} to confirm</Label><Input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></div>
    <DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button variant={definition?.destructive ? 'destructive' : 'default'} disabled={!system || confirmation !== system.code || mutation.isPending} onClick={() => mutation.mutate()}>{definition?.destructive ? <Trash2 className='size-4' /> : <RotateCcw className='size-4' />}{definition?.label}</Button></DialogFooter>
  </DialogContent></Dialog>
}
