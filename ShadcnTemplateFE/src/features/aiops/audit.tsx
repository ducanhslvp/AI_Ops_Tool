import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Eye, Fingerprint } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from './status-badge'

interface AuditRecord { id: string; created_at: string; user_id: string | null; user_email: string | null;
  server_id: string | null; server_hostname: string | null; tool_name: string | null; decision: string | null;
  result: string; duration_ms: number; integrity_hash: string; prompt_preview: string; output_preview: string;
  provider: string | null; model: string | null; request_id: string | null; exit_code: number | null;
  approval_used: boolean }
interface AuditDetail extends AuditRecord { prompt: string | null; reasoning_summary: string | null;
  ssh_command: string | null; output: string | null; provider_input: string | null;
  context_sources: string[]; tool_events: Array<Record<string, unknown>> }

export function AuditPage() {
  const [result, setResult] = useState('')
  const [detailId, setDetailId] = useState<string>()
  const auditQuery = useQuery({ queryKey: ['audit'], queryFn: async () =>
    (await apiClient.get<AuditRecord[]>('/audit', { params: { page: 1, page_size: 200 } })).data })
  const records = (auditQuery.data ?? []).filter((item) => !result || item.result === result || item.decision === result)
  const detailQuery = useQuery({ queryKey: ['audit', 'detail', detailId], enabled: Boolean(detailId), queryFn: async () =>
    (await apiClient.get<AuditDetail>(`/audit/${detailId}`)).data })
  const exportAudit = async () => { try { const response = await apiClient.get('/audit/export', { params: { result: result || undefined }, responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = 'audit.csv'; link.click(); URL.revokeObjectURL(url)
  } catch { toast.error('Audit export failed.') } }
  const exportSelected = (items: AuditRecord[]) => { const fields = ['created_at', 'user_email', 'server_hostname', 'tool_name', 'decision', 'result', 'duration_ms', 'integrity_hash'] as const
    const csv = [fields.join(','), ...items.map((item) => fields.map((field) => JSON.stringify(item[field] ?? '')).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); const link = document.createElement('a'); link.href = url; link.download = 'selected-audit.csv'; link.click(); URL.revokeObjectURL(url) }
  const columns: EnterpriseColumn<AuditRecord>[] = [
    { id: 'time', header: 'Time', accessor: (item) => item.created_at, cell: (item) => new Date(item.created_at).toLocaleString(), size: 180 },
    { id: 'user', header: 'User', accessor: (item) => item.user_email ?? 'System', size: 190 },
    { id: 'target', header: 'Target / Event', accessor: (item) => `${item.server_hostname ?? 'Platform'} ${item.tool_name ?? ''}`, cell: (item) => <div><p className='truncate'>{item.server_hostname ?? 'Platform'}</p><code className='text-xs text-muted-foreground'>{item.tool_name ?? 'event'}</code></div>, size: 190 },
    { id: 'preview', header: 'Prompt / Output preview', accessor: (item) => `${item.prompt_preview} ${item.output_preview}`, cell: (item) => <div className='space-y-1'><p className='truncate text-sm' title={item.prompt_preview}>{item.prompt_preview || 'No prompt recorded'}</p><p className='truncate text-xs text-muted-foreground' title={item.output_preview}>{item.output_preview || 'No output recorded'}</p></div>, size: 360 },
    { id: 'decision', header: 'Decision', accessor: (item) => item.decision ?? item.result, cell: (item) => <StatusBadge value={item.decision ?? item.result} />, size: 140 },
    { id: 'duration', header: 'Duration', accessor: (item) => item.duration_ms, cell: (item) => `${item.duration_ms} ms`, size: 105 },
    { id: 'exit', header: 'Exit', accessor: (item) => item.exit_code ?? '', cell: (item) => item.exit_code ?? '-', size: 70 },
    { id: 'view', header: 'View', accessor: (item) => item.id, enableHiding: false, cell: (item) => <Button size='sm' variant='outline' onClick={() => setDetailId(item.id)}><Eye className='size-4' />View</Button>, size: 100 },
  ]
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4 flex flex-wrap items-center justify-between gap-3'><div><h1 className='text-2xl font-semibold tracking-tight'>Audit Timeline</h1>
      <p className='text-sm text-muted-foreground'>Immutable operations trail with detail and integrity hash.</p></div>
      <Button size='sm' variant='outline' onClick={exportAudit}><Download className='size-4' />Export CSV</Button></div>
    <Card><CardHeader><CardTitle className='flex items-center gap-2 text-base'><Fingerprint className='size-4' />Events</CardTitle></CardHeader>
      <CardContent><EnterpriseDataTable data={records} columns={columns} getRowId={(item) => item.id} entityName='audit record' loading={auditQuery.isLoading}
        searchPlaceholder='Search user, IP target, server, or tool' filterSlot={<select aria-label='Audit result' value={result} onChange={(e) => setResult(e.target.value)} className='h-9 rounded-md border bg-background px-3 text-sm'>
          <option value=''>All results</option>{['success', 'failed', 'denied', 'approval_required'].map((item) => <option key={item}>{item}</option>)}</select>}
        bulkActions={[{ label: 'Export selected', icon: Download, onSelect: exportSelected }]}
        rowPreview={(item) => <AuditPreview item={item} />} />
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
  </Main></>
}
function AuditPreview({ item }: { item: AuditRecord }) { return <div className='space-y-2'><div className='flex items-center justify-between gap-3'><p className='font-medium'>{item.tool_name ?? 'Platform event'}</p><StatusBadge value={item.decision ?? item.result} /></div><div><p className='text-xs font-medium text-muted-foreground'>Prompt</p><p className='mt-0.5 line-clamp-3 whitespace-pre-wrap text-xs'>{item.prompt_preview || 'Not recorded'}</p></div><div><p className='text-xs font-medium text-muted-foreground'>Output</p><p className='mt-0.5 line-clamp-3 whitespace-pre-wrap text-xs'>{item.output_preview || 'Not recorded'}</p></div>{item.request_id && <code className='block truncate text-[11px] text-muted-foreground'>{item.request_id}</code>}</div> }
function Meta({ label, value }: { label: string; value: string | null }) { return <div className='min-w-0'><p className='text-xs text-muted-foreground'>{label}</p><p className='truncate font-medium' title={value ?? undefined}>{value || 'Not recorded'}</p></div> }
function Detail({ label, value, tall = false }: { label: string; value: string | null; tall?: boolean }) { return <div><dt className='font-medium'>{label}</dt><dd className={tall ? 'mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 font-mono text-xs text-muted-foreground' : 'mt-1 max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 text-muted-foreground'}>{value || 'Not recorded'}</dd></div> }
