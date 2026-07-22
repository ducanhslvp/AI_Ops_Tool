import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Eye, GitCompare, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SearchableSelect } from '@/components/searchable-select'
import { ThemeSwitch } from '@/components/theme-switch'
import { ServerTargetSelector, type TargetEnvironment, type TargetServer, type TargetSystem } from '@/components/server-target-selector'
import { StatusBadge } from './status-badge'

interface ReportRecord { id: string; title: string; format: string; system_id: string | null; server_id: string | null; created_at: string }
type SystemRecord = TargetSystem
interface ReportTemplateRecord { id: string; name: string; description: string; format: string }

export function ReportsPage() {
  const client = useQueryClient()
  const [formatFilter, setFormatFilter] = useState('')
  const [preview, setPreview] = useState<{ title: string; content: string }>()
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<ReportRecord>()
  const reportsQuery = useQuery({ queryKey: ['reports'], queryFn: async () =>
    (await apiClient.get<ReportRecord[]>('/reports', { params: { page: 1, page_size: 200 } })).data })
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems'], queryFn: async () =>
    (await apiClient.get<SystemRecord[]>('/inventory/systems')).data })
  const environmentsQuery = useQuery({ queryKey: ['inventory', 'environments', 'report-target'], queryFn: async () =>
    (await apiClient.get<TargetEnvironment[]>('/inventory/environments', { params: { page: 1, page_size: 200 } })).data })
  const serversQuery = useQuery({ queryKey: ['inventory', 'servers', 'report-target'], queryFn: async () =>
    (await apiClient.get<TargetServer[]>('/inventory/servers', { params: { page: 1, page_size: 200 } })).data })
  const templatesQuery = useQuery({ queryKey: ['reports', 'templates'], queryFn: async () =>
    (await apiClient.get<ReportTemplateRecord[]>('/reports/templates')).data })
  const reports = (reportsQuery.data ?? []).filter((report) => !formatFilter || report.format === formatFilter)
  const exportList = (records: ReportRecord[] = reports) => {
    const csv = ['title,format,system_id,server_id,created_at', ...records.map((report) =>
      [report.title, report.format, report.system_id ?? '', report.server_id ?? '', report.created_at]
        .map((value) => `"${String(value).replace(/"/g, '""')}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'report-history.csv'; anchor.click(); URL.revokeObjectURL(url)
  }
  const remove = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/reports/${id}`), onSuccess: async () => {
    setDeleting(undefined); await client.invalidateQueries({ queryKey: ['reports'] }); toast.success('Report deleted.')
  }, onError: () => toast.error('Report could not be deleted.') })
  const showPreview = async (report: ReportRecord) => { try {
    const response = await apiClient.get<{ content: string }>(`/reports/${report.id}`)
    setPreview({ title: report.title, content: response.data.content })
  } catch { toast.error('Preview could not be loaded.') } }
  const showComparison = async (report: ReportRecord) => { try {
    const response = await apiClient.get<{ diff: string }>(`/reports/${report.id}/compare-latest`)
    setPreview({ title: `Compare: ${report.title}`, content: response.data.diff })
  } catch { toast.error('Comparison could not be loaded.') } }
  const download = async (report: ReportRecord) => { try {
    const response = await apiClient.get(`/reports/${report.id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const anchor = document.createElement('a'); anchor.href = url
    anchor.download = `${report.title}.${report.format === 'markdown' ? 'md' : report.format}`; anchor.click(); URL.revokeObjectURL(url)
  } catch { toast.error('Download failed.') } }
  const columns: EnterpriseColumn<ReportRecord>[] = [
    { id: 'title', header: 'Report', accessor: (report) => report.title, cell: (report) => <div className='min-w-0'><p className='truncate font-medium'>{report.title}</p><p className='truncate text-xs text-muted-foreground'>{reportTarget(report, systemsQuery.data ?? [], serversQuery.data ?? [])}</p></div>, size: 340 },
    { id: 'format', header: 'Format', accessor: (report) => report.format, cell: (report) => <StatusBadge value={report.format} />, size: 120 },
    { id: 'created', header: 'Generated', accessor: (report) => report.created_at, cell: (report) => new Date(report.created_at).toLocaleString(), size: 190 },
    { id: 'actions', header: 'Actions', accessor: (report) => report.id, enableHiding: false, size: 176, cell: (report) => <div className='flex items-center justify-end gap-1'>
      <Button title='Preview report' aria-label={`Preview ${report.title}`} size='icon' variant='ghost' onClick={() => void showPreview(report)}><Eye className='size-4' /></Button>
      <Button title='Compare report' aria-label={`Compare ${report.title}`} size='icon' variant='ghost' onClick={() => void showComparison(report)}><GitCompare className='size-4' /></Button>
      <Button title='Download report' aria-label={`Download ${report.title}`} size='icon' variant='ghost' onClick={() => void download(report)}><Download className='size-4' /></Button>
      <Button title='Delete report' aria-label={`Delete ${report.title}`} size='icon' variant='ghost' onClick={() => setDeleting(report)}><Trash2 className='size-4' /></Button>
    </div> },
  ]
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4 flex flex-wrap items-center justify-between gap-3'><div><h1 className='text-2xl font-semibold tracking-tight'>Reports</h1>
      <p className='text-sm text-muted-foreground'>Reports generated from current database and audited evidence.</p></div>
      <div className='flex gap-2'><Button size='sm' variant='outline' onClick={() => exportList()}><Download className='size-4' />Export</Button>
        <Button size='sm' onClick={() => setCreating(true)}><Plus className='size-4' />Generate report</Button></div></div>
    <Card><CardContent className='pt-6'><EnterpriseDataTable data={reports} columns={columns} getRowId={(report) => report.id}
      entityName='report' loading={reportsQuery.isLoading} searchPlaceholder='Search report history'
      filterSlot={<SearchableSelect ariaLabel='Report format' value={formatFilter} allowClear placeholder='All formats' className='w-44'
        options={['markdown', 'html', 'pdf', 'csv'].map((format) => ({ value: format, label: format.toUpperCase() }))} onValueChange={setFormatFilter} />}
      bulkActions={[{ label: 'Export selected', icon: Download, onSelect: exportList }]} /></CardContent></Card>
    <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && setPreview(undefined)}><DialogContent className='max-h-[80svh] max-w-3xl overflow-auto'>
      <DialogHeader><DialogTitle>{preview?.title}</DialogTitle><DialogDescription>Persisted report content</DialogDescription></DialogHeader>
      <pre className='whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-xs'>{preview?.content}</pre></DialogContent></Dialog>
    <CreateReport open={creating} onOpenChange={setCreating} systems={systemsQuery.data ?? []} environments={environmentsQuery.data ?? []}
      servers={serversQuery.data ?? []} templates={templatesQuery.data ?? []} />
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)} title='Delete report?'
      desc='The generated report and its history entry will be removed.' destructive isLoading={remove.isPending}
      handleConfirm={() => deleting && remove.mutate(deleting.id)} />
  </Main></>
}

function reportTarget(report: ReportRecord, systems: SystemRecord[], servers: TargetServer[]) {
  const server = servers.find((item) => item.id === report.server_id)
  if (server) return `${server.hostname} (${server.ip_address})`
  const system = systems.find((item) => item.id === report.system_id)
  return system ? `${system.code} / all servers` : 'Entire platform'
}

function CreateReport({ open, onOpenChange, systems, environments, servers, templates }: { open: boolean; onOpenChange: (open: boolean) => void;
  systems: SystemRecord[]; environments: TargetEnvironment[]; servers: TargetServer[]; templates: ReportTemplateRecord[] }) {
  const client = useQueryClient(); const [title, setTitle] = useState(''); const [format, setFormat] = useState('markdown'); const [systemId, setSystemId] = useState('')
  const [templateId, setTemplateId] = useState(''); const [serverId, setServerId] = useState(''); const [scope, setScope] = useState<'system' | 'server'>('system')
  const create = useMutation({ mutationFn: async () => apiClient.post('/reports', { title, format, system_id: systemId || null,
    server_id: scope === 'server' ? serverId || null : null, template_id: templateId || null }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['reports'] }); onOpenChange(false); setTitle(''); toast.success('Report generated from live evidence.') },
    onError: () => toast.error('Report generation failed.') })
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Generate report</DialogTitle>
    <DialogDescription>The backend reads current inventory, alerts and audit records.</DialogDescription></DialogHeader>
    <form id='report-form' className='space-y-4' onSubmit={(event) => { event.preventDefault(); create.mutate() }}><div className='space-y-1'><Label>Title</Label>
      <Input required minLength={3} value={title} onChange={(event) => setTitle(event.target.value)} /></div><div className='flex h-9 rounded-md border p-0.5'><Button type='button' size='sm' variant={scope === 'system' ? 'secondary' : 'ghost'} onClick={() => { setScope('system'); setServerId('') }}>System report</Button><Button type='button' size='sm' variant={scope === 'server' ? 'secondary' : 'ghost'} onClick={() => setScope('server')}>Server report</Button></div>
      {scope === 'system' ? <div className='space-y-1'><Label>System</Label><SearchableSelect ariaLabel='Report system' value={systemId} allowClear placeholder='Entire platform'
        searchPlaceholder='Search systems...' options={systems.map((system) => ({ value: system.id, label: `${system.code} - ${system.name}` }))} onValueChange={setSystemId} /></div> :
        <ServerTargetSelector systems={systems} environments={environments} servers={servers} value={serverId} onChange={(id) => { setServerId(id); const server = servers.find((item) => item.id === id); if (server) setSystemId(server.system_id) }} />}
      <div className='space-y-1'><Label>Template</Label><SearchableSelect ariaLabel='Report template' value={templateId} allowClear placeholder='Standard evidence report'
        searchPlaceholder='Search report templates...' options={templates.map((template) => ({ value: template.id, label: template.name, keywords: template.description }))} onValueChange={setTemplateId} /></div>
      <div className='space-y-1'><Label>Format</Label><SearchableSelect ariaLabel='Report output format' value={format}
        options={['markdown', 'html', 'pdf', 'csv'].map((item) => ({ value: item, label: item.toUpperCase() }))} onValueChange={setFormat} /></div></form>
    <DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='report-form' type='submit' disabled={create.isPending || (scope === 'server' && !serverId)}>Generate</Button></DialogFooter>
  </DialogContent></Dialog>
}
