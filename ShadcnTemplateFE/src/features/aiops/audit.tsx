import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarRange, Download, Eye, Fingerprint, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { SearchableSelect } from '@/components/searchable-select'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from './status-badge'

interface AuditRecord { id: string; created_at: string; user_id: string | null; user_email: string | null;
  server_id: string | null; server_hostname: string | null; server_ip: string | null; system_code: string | null;
  tool_name: string | null; ssh_command: string | null; decision: string | null;
  result: string; duration_ms: number; integrity_hash: string; prompt_preview: string; output_preview: string;
  provider: string | null; model: string | null; request_id: string | null; exit_code: number | null;
  approval_used: boolean }
interface SystemRecord { id: string; code: string; name: string }
interface ServerRecord { id: string; system_id: string; hostname: string; ip_address: string }
interface AuditDetail extends AuditRecord { prompt: string | null; reasoning_summary: string | null;
  ssh_command: string | null; output: string | null; provider_input: string | null;
  context_sources: string[]; tool_events: Array<Record<string, unknown>> }

export function AuditPage() {
  const queryClient = useQueryClient()
  const [result, setResult] = useState('')
  const [detailId, setDetailId] = useState<string>()
  const [deleting, setDeleting] = useState<AuditRecord>()
  const [bulkDeleting, setBulkDeleting] = useState<AuditRecord[]>([])
  const [rangeOpen, setRangeOpen] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const initialParams = new URLSearchParams(window.location.search)
  const [auditMode, setAuditMode] = useState<'activity' | 'ssh'>(initialParams.get('mode') === 'ssh' ? 'ssh' : 'activity')
  const [systemId, setSystemId] = useState(initialParams.get('system_id') ?? '')
  const [serverId, setServerId] = useState(initialParams.get('server_id') ?? '')
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems', 'audit'], queryFn: async () =>
    (await apiClient.get<SystemRecord[]>('/inventory/systems', { params: { page: 1, page_size: 1000 } })).data })
  const serversQuery = useQuery({ queryKey: ['inventory', 'servers', 'audit'], queryFn: async () =>
    (await apiClient.get<ServerRecord[]>('/inventory/servers', { params: { page: 1, page_size: 1000 } })).data })
  const auditQuery = useQuery({ queryKey: ['audit', auditMode, systemId, serverId], queryFn: async () =>
    (await apiClient.get<AuditRecord[]>('/audit', { params: { page: 1, page_size: 1000,
      ssh_only: auditMode === 'ssh' || undefined, system_id: systemId || undefined,
      server_id: serverId || undefined } })).data })
  const records = (auditQuery.data ?? []).filter((item) => !result || item.result === result || item.decision === result)
  const detailQuery = useQuery({ queryKey: ['audit', 'detail', detailId], enabled: Boolean(detailId), queryFn: async () =>
    (await apiClient.get<AuditDetail>(`/audit/${detailId}`)).data })
  const invalidate = async () => queryClient.invalidateQueries({ queryKey: ['audit'] })
  const deleteOne = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/audit/${id}`),
    onSuccess: async () => { setDeleting(undefined); await invalidate(); toast.success('Audit record deleted and integrity chain rebuilt.') },
    onError: () => toast.error('Audit record could not be deleted.') })
  const deleteMany = useMutation({ mutationFn: async (items: AuditRecord[]) => apiClient.post('/audit/actions/bulk-delete', { ids: items.map((item) => item.id) }),
    onSuccess: async () => { setBulkDeleting([]); await invalidate(); toast.success('Selected audit records deleted.') },
    onError: () => toast.error('Selected audit records could not be deleted.') })
  const deleteRange = useMutation({ mutationFn: async () => apiClient.post('/audit/actions/delete-range', {
    date_from: new Date(dateFrom).toISOString(), date_to: new Date(dateTo).toISOString(),
  }), onSuccess: async () => { setRangeOpen(false); await invalidate(); toast.success('Audit range deleted and integrity chain rebuilt.') },
    onError: () => toast.error('Audit range could not be deleted.') })
  const exportAudit = async () => { try { const response = await apiClient.get('/audit/export', { params: { result: result || undefined }, responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = 'audit.csv'; link.click(); URL.revokeObjectURL(url)
  } catch { toast.error('Audit export failed.') } }
  const exportSelected = (items: AuditRecord[]) => { const fields = ['created_at', 'user_email', 'server_hostname', 'tool_name', 'decision', 'result', 'duration_ms', 'integrity_hash'] as const
    const csv = [fields.join(','), ...items.map((item) => fields.map((field) => JSON.stringify(item[field] ?? '')).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); const link = document.createElement('a'); link.href = url; link.download = 'selected-audit.csv'; link.click(); URL.revokeObjectURL(url) }
  const activityColumns: EnterpriseColumn<AuditRecord>[] = [
    { id: 'time', header: 'Time', accessor: (item) => item.created_at, cell: (item) => new Date(item.created_at).toLocaleString(), size: 180 },
    { id: 'user', header: 'User', accessor: (item) => item.user_email ?? 'System', size: 190 },
    { id: 'target', header: 'Target / Event', accessor: (item) => `${item.server_hostname ?? 'Platform'} ${item.tool_name ?? ''}`, cell: (item) => <div><p className='truncate'>{item.server_hostname ?? 'Platform'}</p><code className='text-xs text-muted-foreground'>{item.tool_name ?? 'event'}</code></div>, size: 190 },
    { id: 'preview', header: 'Prompt / Output preview', accessor: (item) => `${item.prompt_preview} ${item.output_preview}`, cell: (item) => <div className='space-y-1'><p className='truncate text-sm' title={item.prompt_preview}>{item.prompt_preview || 'No prompt recorded'}</p><p className='truncate text-xs text-muted-foreground' title={item.output_preview}>{item.output_preview || 'No output recorded'}</p></div>, size: 360 },
    { id: 'decision', header: 'Decision', accessor: (item) => item.decision ?? item.result, cell: (item) => <StatusBadge value={item.decision ?? item.result} />, size: 140 },
    { id: 'duration', header: 'Duration', accessor: (item) => item.duration_ms, cell: (item) => `${item.duration_ms} ms`, size: 105 },
    { id: 'exit', header: 'Exit', accessor: (item) => item.exit_code ?? '', cell: (item) => item.exit_code ?? '-', size: 70 },
    { id: 'actions', header: 'Actions', accessor: (item) => item.id, enableHiding: false,
      cell: (item) => <div className='flex items-center gap-2'><Button className='w-24' size='sm' variant='outline' onClick={() => setDetailId(item.id)}><Eye className='size-4' />View</Button>
        <Button className='w-24' size='sm' variant='outline' onClick={() => setDeleting(item)}><Trash2 className='size-4' />Delete</Button></div>, size: 220 },
  ]
  const sshColumns: EnterpriseColumn<AuditRecord>[] = [
    { id: 'time', header: 'Time', accessor: (item) => item.created_at, cell: (item) => new Date(item.created_at).toLocaleString(), size: 180 },
    { id: 'user', header: 'User', accessor: (item) => item.user_email ?? 'System', size: 190 },
    { id: 'target', header: 'System / Server', accessor: (item) => `${item.system_code ?? ''} ${item.server_hostname ?? ''} ${item.server_ip ?? ''}`,
      cell: (item) => <div><p className='font-medium'>{item.system_code ?? 'Unassigned'} / {item.server_hostname ?? 'Unknown server'}</p><p className='text-xs text-muted-foreground'>{item.server_ip ?? 'No IP recorded'}</p></div>, size: 250 },
    { id: 'command', header: 'SSH command', accessor: (item) => item.ssh_command ?? '',
      cell: (item) => <code className='block max-w-[32rem] truncate text-xs' title={item.ssh_command ?? undefined}>{item.ssh_command ?? 'Not recorded'}</code>, size: 360 },
    { id: 'output', header: 'Result preview', accessor: (item) => item.output_preview,
      cell: (item) => <p className='line-clamp-2 whitespace-pre-wrap font-mono text-xs text-muted-foreground' title={item.output_preview}>{item.output_preview || 'No output returned'}</p>, size: 360 },
    { id: 'decision', header: 'Status', accessor: (item) => item.decision ?? item.result, cell: (item) => <StatusBadge value={item.result} />, size: 120 },
    { id: 'exit', header: 'Exit', accessor: (item) => item.exit_code ?? '', cell: (item) => item.exit_code ?? '-', size: 70 },
    { id: 'duration', header: 'Duration', accessor: (item) => item.duration_ms, cell: (item) => `${item.duration_ms} ms`, size: 105 },
    { id: 'actions', header: 'Actions', accessor: (item) => item.id, enableHiding: false,
      cell: (item) => <div className='flex items-center gap-2'><Button className='w-24' size='sm' variant='outline' onClick={() => setDetailId(item.id)}><Eye className='size-4' />View</Button>
        <Button className='w-24' size='sm' variant='outline' onClick={() => setDeleting(item)}><Trash2 className='size-4' />Delete</Button></div>, size: 220 },
  ]
  const columns = auditMode === 'ssh' ? sshColumns : activityColumns
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4 flex flex-wrap items-center justify-between gap-3'><div><h1 className='text-2xl font-semibold tracking-tight'>Audit Timeline</h1>
      <p className='text-sm text-muted-foreground'>Integrity-chained operations trail with controlled administrative retention.</p></div>
      <div className='flex gap-2'><Button size='sm' variant='outline' onClick={() => setRangeOpen(true)}><CalendarRange className='size-4' />Delete by date</Button>
        <Button size='sm' variant='outline' onClick={exportAudit}><Download className='size-4' />Export CSV</Button></div></div>
    <Tabs value={auditMode} onValueChange={(value) => { setAuditMode(value as 'activity' | 'ssh'); setSystemId(''); setServerId('') }} className='mb-4'>
      <TabsList><TabsTrigger value='activity'>Activity Audit</TabsTrigger><TabsTrigger value='ssh'>SSH Commands</TabsTrigger></TabsList>
    </Tabs>
    <Card><CardHeader><CardTitle className='flex items-center gap-2 text-base'><Fingerprint className='size-4' />{auditMode === 'ssh' ? 'Commands executed against servers' : 'Conversations and platform activity'}</CardTitle></CardHeader>
      <CardContent><EnterpriseDataTable data={records} columns={columns} getRowId={(item) => item.id} entityName='audit record' loading={auditQuery.isLoading}
        searchPlaceholder={auditMode === 'ssh' ? 'Search server, command or short result' : 'Search user, server, prompt, output or event'} filterSlot={<><SearchableSelect className='w-52' ariaLabel='Audit System' allowClear value={systemId} placeholder='All Systems'
          searchPlaceholder='Search Systems...' options={(systemsQuery.data ?? []).map((item) => ({ value: item.id, label: `${item.code} - ${item.name}` }))}
          onValueChange={(value) => { setSystemId(value); setServerId('') }} />
          <SearchableSelect className='w-56' ariaLabel='Audit server' allowClear value={serverId} placeholder='All servers'
            searchPlaceholder='Search server or IP...' options={(serversQuery.data ?? []).filter((item) => !systemId || item.system_id === systemId).map((item) => ({ value: item.id, label: `${item.hostname} - ${item.ip_address}` }))}
            onValueChange={setServerId} />
          <select aria-label='Audit result' value={result} onChange={(e) => setResult(e.target.value)} className='h-9 rounded-md border bg-background px-3 text-sm'>
          <option value=''>All results</option>{['success', 'failed', 'denied', 'approval_required'].map((item) => <option key={item}>{item}</option>)}</select></>}
        bulkActions={[{ label: 'Export selected', icon: Download, onSelect: exportSelected },
          { label: 'Delete selected', icon: Trash2, destructive: true, onSelect: setBulkDeleting }]}
        rowPreviewDelayMs={550} rowPreview={(item) => <AuditPreview item={item} />} />
      </CardContent></Card>
    <Dialog open={Boolean(detailId)} onOpenChange={(open) => !open && setDetailId(undefined)}><DialogContent className='max-h-[90svh] max-w-[min(96vw,1100px)] overflow-auto'>
      <DialogHeader><DialogTitle>Audit evidence</DialogTitle><DialogDescription>Immutable record {detailQuery.data?.integrity_hash}</DialogDescription></DialogHeader>
      {detailQuery.data && <div className='space-y-4 text-sm'><div className='grid gap-3 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-6'><Meta label='Provider' value={detailQuery.data.provider} /><Meta label='Model' value={detailQuery.data.model} /><Meta label='Request ID' value={detailQuery.data.request_id} /><Meta label='Duration' value={`${detailQuery.data.duration_ms} ms`} /><Meta label='Exit code' value={detailQuery.data.exit_code == null ? null : String(detailQuery.data.exit_code)} /><Meta label='Approval' value={detailQuery.data.approval_used ? 'Used' : 'Not used'} /></div><dl className='grid gap-3'>
        <Detail label='User prompt' value={detailQuery.data.prompt} />
        <Detail label='Exact provider input' value={detailQuery.data.provider_input} tall />
        <Detail label='Workspace context sources' value={detailQuery.data.context_sources.join('\n')} />
        <Detail label='Tool execution events' value={JSON.stringify(detailQuery.data.tool_events, null, 2)} tall />
        <Detail label='Reasoning summary' value={detailQuery.data.reasoning_summary} />
        <Detail label='Backend mapped command' value={detailQuery.data.ssh_command} />
        <Detail label='Output returned' value={detailQuery.data.output} tall />
      </dl></div>}
    </DialogContent></Dialog>
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}
      title='Delete audit record?' desc='This administrative maintenance action rebuilds the integrity chain for all remaining records.'
      destructive isLoading={deleteOne.isPending} handleConfirm={() => deleting && deleteOne.mutate(deleting.id)} />
    <ConfirmDialog open={bulkDeleting.length > 0} onOpenChange={(open) => !open && setBulkDeleting([])}
      title={`Delete ${bulkDeleting.length} audit records?`}
      desc='This cannot be undone. The integrity chain is rebuilt for all records that remain.'
      destructive isLoading={deleteMany.isPending} handleConfirm={() => deleteMany.mutate(bulkDeleting)} />
    <Dialog open={rangeOpen} onOpenChange={setRangeOpen}><DialogContent className='sm:max-w-[80vw]'>
      <DialogHeader><DialogTitle>Delete audit records by date</DialogTitle>
        <DialogDescription>Both boundaries are inclusive. The remaining audit chain is rebuilt after deletion.</DialogDescription></DialogHeader>
      <div><Label className='mb-2 block'>Quick retention cutoff</Label><div className='flex flex-wrap gap-2'>
        {[['30 days', 30], ['60 days', 60], ['90 days', 90], ['180 days', 180], ['1 year', 365]].map(([label, days]) =>
          <Button key={String(label)} size='sm' variant='outline' onClick={() => {
            const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - Number(days))
            setDateFrom('1970-01-01T00:00'); setDateTo(cutoff.toISOString().slice(0, 16))
          }}>{label}</Button>)}
      </div><p className='mt-2 text-xs text-muted-foreground'>A preset selects all records older than its retention period.</p></div>
      <div className='grid gap-4 sm:grid-cols-2'><div><Label className='mb-1.5 block'>From</Label><Input type='datetime-local' value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></div>
        <div><Label className='mb-1.5 block'>To</Label><Input type='datetime-local' value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></div></div>
      <DialogFooter><Button variant='outline' onClick={() => setRangeOpen(false)}>Cancel</Button><Button variant='destructive'
        disabled={!dateFrom || !dateTo || deleteRange.isPending || new Date(dateTo) < new Date(dateFrom)}
        onClick={() => deleteRange.mutate()}><Trash2 className='size-4' />Delete range</Button></DialogFooter>
    </DialogContent></Dialog>
  </Main></>
}
function AuditPreview({ item }: { item: AuditRecord }) { return <div className='space-y-2'><div className='flex items-center justify-between gap-3'><p className='font-medium'>{item.tool_name ?? 'Platform event'}</p><StatusBadge value={item.decision ?? item.result} /></div><div><p className='text-xs font-medium text-muted-foreground'>Prompt</p><p className='mt-0.5 line-clamp-3 whitespace-pre-wrap text-xs'>{item.prompt_preview || 'Not recorded'}</p></div><div><p className='text-xs font-medium text-muted-foreground'>Output</p><p className='mt-0.5 line-clamp-3 whitespace-pre-wrap text-xs'>{item.output_preview || 'Not recorded'}</p></div>{item.request_id && <code className='block truncate text-[11px] text-muted-foreground'>{item.request_id}</code>}</div> }
function Meta({ label, value }: { label: string; value: string | null }) { return <div className='min-w-0'><p className='text-xs text-muted-foreground'>{label}</p><p className='truncate font-medium' title={value ?? undefined}>{value || 'Not recorded'}</p></div> }
function Detail({ label, value, tall = false }: { label: string; value: string | null; tall?: boolean }) { return <div><dt className='font-medium'>{label}</dt><dd className={tall ? 'mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 font-mono text-xs text-muted-foreground' : 'mt-1 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 text-muted-foreground'}>{value || 'Not recorded'}</dd></div> }
