import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Download, Eye, FileDown, FileUp, Pencil, Plus, Server as ServerIcon, Trash2, Wifi } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient, getPaginated } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SearchableSelect } from '@/components/searchable-select'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from './status-badge'

type Resource = 'systems' | 'servers' | 'credentials' | 'environments'
interface BaseRecord { id: string; name?: string; created_at: string }
interface SystemRecord extends BaseRecord { code: string; name: string; owner: string; description: string; criticality: string; default_credential_id: string | null }
interface EnvironmentRecord extends BaseRecord { name: string; description: string; risk_weight: number }
interface CredentialRecord extends BaseRecord { name: string; system_id: string | null; username: string; provider: string; metadata_json: Record<string, unknown>; is_active: boolean }
interface ServerRecord extends BaseRecord { system_id: string; environment_id: string; credential_id: string | null;
  hostname: string; ip_address: string; os: string; server_type: string; role: string; description: string;
  tags: string[]; status: string; ssh_config: Record<string, unknown>; credential_username: string; credential_scope: string }
type InventoryRecord = SystemRecord | EnvironmentRecord | CredentialRecord | ServerRecord
interface KnowledgeRecord { id: string; system_id: string; title: string; document_type: string; updated_at: string }
interface SystemDetail { system: SystemRecord; servers: ServerRecord[]; knowledge: KnowledgeRecord[] }
interface ImportResult { created: number; updated: number; failed: number; errors: Array<{ row: number; error: string }> }

const resourceLabels: Record<Resource, string> = {
  servers: 'server',
  systems: 'system',
  environments: 'environment',
  credentials: 'SSH credential',
}

const emptyForms = {
  systems: { name: '', code: '', owner: '', description: '', criticality: 'medium', default_credential_id: '' },
  environments: { name: '', description: '', risk_weight: 1 },
  credentials: { name: '', system_id: '', username: '', password: '', is_active: true },
  servers: { hostname: '', ip_address: '', os: 'Ubuntu 24.04', server_type: 'linux', role: '',
    description: '', tags: '', system_id: '', environment_id: '', credential_id: '', port: 22 },
}

export function InventoryPage() {
  const client = useQueryClient()
  const importInputRef = useRef<HTMLInputElement>(null)
  const [resource, setResource] = useState<Resource>('systems')
  const [statusFilter, setStatusFilter] = useState('')
  const [systemFilter, setSystemFilter] = useState('')
  const [environmentFilter, setEnvironmentFilter] = useState('')
  const [editing, setEditing] = useState<InventoryRecord | null | undefined>()
  const [deleting, setDeleting] = useState<InventoryRecord>()
  const [viewingSystem, setViewingSystem] = useState<SystemRecord>()
  const [defaultSystemId, setDefaultSystemId] = useState('')
  const [importReport, setImportReport] = useState<ImportResult>()
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems'], queryFn: async () =>
    (await apiClient.get<SystemRecord[]>('/inventory/systems', { params: { page: 1, page_size: 1000 } })).data })
  const serversQuery = useQuery({ queryKey: ['inventory', 'servers'], queryFn: () =>
    getPaginated<ServerRecord>('/inventory/servers', { page: 1, page_size: 200 }) })
  const environmentsQuery = useQuery({ queryKey: ['inventory', 'environments'], queryFn: async () =>
    (await apiClient.get<EnvironmentRecord[]>('/inventory/environments', { params: { page: 1, page_size: 1000 } })).data })
  const credentialsQuery = useQuery({ queryKey: ['inventory', 'credentials'], queryFn: async () =>
    (await apiClient.get<CredentialRecord[]>('/inventory/credentials', { params: { page: 1, page_size: 1000 } })).data })
  const systemDetailQuery = useQuery({ queryKey: ['inventory', 'system-detail', viewingSystem?.id], enabled: Boolean(viewingSystem),
    queryFn: async () => (await apiClient.get<SystemDetail>(`/inventory/systems/${viewingSystem?.id}`)).data })
  const loadedRecords = useMemo(() => {
    const dataByResource: Record<Resource, InventoryRecord[]> = {
      systems: systemsQuery.data ?? [],
      servers: serversQuery.data?.items ?? [],
      environments: environmentsQuery.data ?? [],
      credentials: credentialsQuery.data ?? [],
    }
    return dataByResource[resource]
  }, [credentialsQuery.data, environmentsQuery.data, resource, serversQuery.data, systemsQuery.data])
  const filtered = useMemo(() => loadedRecords.filter((item) => !statusFilter || statusValue(item) === statusFilter)
    .filter((item) => resource !== 'servers' || (!systemFilter || (item as ServerRecord).system_id === systemFilter))
    .filter((item) => resource !== 'servers' || (!environmentFilter || (item as ServerRecord).environment_id === environmentFilter)),
  [environmentFilter, loadedRecords, resource, statusFilter, systemFilter])
  const remove = useMutation({ mutationFn: async (item: InventoryRecord) =>
    apiClient.delete(`/inventory/${resource}/${item.id}`), onSuccess: async () => {
      setDeleting(undefined); await client.invalidateQueries({ queryKey: ['inventory', resource] })
      toast.success('Inventory record deleted.')
    }, onError: () => toast.error('Record could not be deleted. Check dependencies.') })
  const bulkRemove = useMutation({ mutationFn: async (items: InventoryRecord[]) =>
    Promise.all(items.map((item) => apiClient.delete(`/inventory/${resource}/${item.id}`))), onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['inventory', resource] }); toast.success('Selected inventory records deleted.')
    }, onError: () => toast.error('Some selected records are protected or referenced.') })
  const testConnection = useMutation({ mutationFn: async (id: string) =>
    (await apiClient.post<{ connected: boolean }>(`/inventory/servers/${id}/test-connection`)).data,
    onSuccess: async (result) => { await client.invalidateQueries({ queryKey: ['inventory', 'servers'] })
      toast[result.connected ? 'success' : 'error'](result.connected ? 'Connection verified.' : 'Connection failed.') },
    onError: () => toast.error('SSH connection could not be established.') })
  const importExcel = useMutation({ mutationFn: async (file: File) => { const form = new FormData(); form.append('file', file)
    return (await apiClient.post<ImportResult>(`/inventory/${resource}/import`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data },
    onSuccess: async (result) => { setImportReport(result); await client.invalidateQueries({ queryKey: ['inventory'] }); toast[result.failed ? 'warning' : 'success'](`Import complete: ${result.created} created, ${result.updated} updated, ${result.failed} failed.`) },
    onError: () => toast.error('Excel import failed. Download the current template and validate all required columns.') })
  const downloadTemplate = async () => { try { const response = await apiClient.get(`/inventory/${resource}/import-template`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = `aiops-${resource}-import.xlsx`; link.click(); URL.revokeObjectURL(url)
  } catch { toast.error('Import template could not be downloaded.') } }

  const exportCsv = (records: InventoryRecord[] = filtered) => {
    const columns = resource === 'servers' ? ['hostname', 'ip_address', 'os', 'status'] : ['name', 'id']
    const value = [columns.join(','), ...records.map((item) => columns.map((key) =>
      `"${String((item as unknown as Record<string, unknown>)[key] ?? '').replace(/"/g, '""')}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([value], { type: 'text/csv' }))
    const link = document.createElement('a'); link.href = url; link.download = `${resource}.csv`; link.click()
    URL.revokeObjectURL(url)
  }
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4 flex flex-wrap items-center justify-between gap-3'><div>
      <h1 className='text-2xl font-semibold tracking-tight'>Inventory</h1>
      <p className='text-sm text-muted-foreground'>Manage infrastructure records through audited APIs.</p></div>
      <div className='flex flex-wrap gap-2'><input ref={importInputRef} type='file' accept='.xlsx' className='hidden' onChange={(event) => { const file = event.target.files?.[0]; if (file) importExcel.mutate(file); event.target.value = '' }} />
        {(resource === 'systems' || resource === 'servers') && <><Button size='sm' variant='outline' onClick={() => void downloadTemplate()}><FileDown className='size-4' />Template</Button><Button size='sm' variant='outline' disabled={importExcel.isPending} onClick={() => importInputRef.current?.click()}><FileUp className='size-4' />Import Excel</Button></>}
        <Button size='sm' variant='outline' onClick={() => exportCsv()}><Download className='size-4' />Export</Button>
        <Button size='sm' onClick={() => { setDefaultSystemId(''); setEditing(null) }}><Plus className='size-4' />Add {resourceLabels[resource]}</Button></div></div>
    <Tabs value={resource} onValueChange={(value) => { setResource(value as Resource); setStatusFilter(''); setSystemFilter(''); setEnvironmentFilter('') }}>
      <TabsList><TabsTrigger value='systems'>Systems</TabsTrigger><TabsTrigger value='servers'>Servers</TabsTrigger>
        <TabsTrigger value='credentials'>SSH credentials</TabsTrigger><TabsTrigger value='environments'>Environments</TabsTrigger></TabsList>
    </Tabs>
    <Card className='mt-4'><CardContent className='p-4'>
      <EnterpriseDataTable data={filtered} columns={inventoryColumns(resource, systemsQuery.data ?? [], environmentsQuery.data ?? [])}
        getRowId={(item) => item.id} loading={resource === 'servers' ? serversQuery.isLoading : resource === 'systems' ? systemsQuery.isLoading : resource === 'environments' ? environmentsQuery.isLoading : credentialsQuery.isLoading}
        searchPlaceholder={`Search loaded ${resource}`} entityName={resourceLabels[resource]} filterSlot={<><SearchableSelect ariaLabel='Filter status' value={statusFilter} allowClear placeholder='All statuses' className='w-44'
          options={[...new Set(loadedRecords.map(statusValue))].map((value) => ({ value, label: value }))} onValueChange={setStatusFilter} />
          {resource === 'servers' && <><SearchableSelect ariaLabel='Filter server system' value={systemFilter} allowClear placeholder='All systems' className='w-56'
            options={(systemsQuery.data ?? []).map((system) => ({ value: system.id, label: `${system.code} - ${system.name}` }))} onValueChange={(value) => { setSystemFilter(value); setEnvironmentFilter('') }} />
            <SearchableSelect ariaLabel='Filter server environment' value={environmentFilter} allowClear placeholder='All environments' className='w-48'
              options={(environmentsQuery.data ?? []).map((environment) => ({ value: environment.id, label: environment.name }))} onValueChange={setEnvironmentFilter} /></>}</>}
        rowActions={[{ label: 'View System', icon: Eye, hidden: (item) => !('code' in item), onSelect: (item) => setViewingSystem(item as SystemRecord) },
          { label: 'Test connection', icon: Wifi, hidden: (item) => !('hostname' in item), onSelect: (item) => testConnection.mutate(item.id) },
          { label: 'Edit', icon: Pencil, onSelect: setEditing }, { label: 'Delete', icon: Trash2, destructive: true, onSelect: setDeleting }]}
        bulkActions={[{ label: 'Export selected', icon: Download, onSelect: exportCsv }, { label: 'Delete selected', icon: Trash2, destructive: true, onSelect: (items) => bulkRemove.mutate(items) }]}
        emptyTitle={`No ${resource} found`} emptyDescription='Adjust the current System, Environment, status, or search filters.' />
    </CardContent></Card>
    <InventoryDialog key={`${resource}-${editing?.id ?? 'new'}-${editing !== undefined}-${defaultSystemId}`} resource={resource} record={editing} systems={systemsQuery.data ?? []}
      environments={environmentsQuery.data ?? []} credentials={credentialsQuery.data ?? []}
      defaultSystemId={defaultSystemId} open={editing !== undefined} onOpenChange={(open) => !open && setEditing(undefined)} />
    <SystemDetailsDialog system={viewingSystem} detail={systemDetailQuery.data} loading={systemDetailQuery.isLoading}
      onOpenChange={(open) => !open && setViewingSystem(undefined)} onEditSystem={(item) => { setViewingSystem(undefined); setResource('systems'); setEditing(item) }}
      onAddServer={(systemId) => { setViewingSystem(undefined); setResource('servers'); setDefaultSystemId(systemId); setEditing(null) }}
      onEditServer={(item) => { setViewingSystem(undefined); setResource('servers'); setEditing(item) }}
      onDeleteServer={(item) => { setViewingSystem(undefined); setResource('servers'); setDeleting(item) }} />
    <Dialog open={Boolean(importReport)} onOpenChange={(open) => !open && setImportReport(undefined)}><DialogContent className='max-h-[85svh] overflow-auto sm:max-w-2xl'><DialogHeader><DialogTitle>Excel import result</DialogTitle><DialogDescription>{importReport ? `${importReport.created} created, ${importReport.updated} updated, ${importReport.failed} failed.` : ''}</DialogDescription></DialogHeader>
      {importReport?.errors.length ? <div className='divide-y rounded-md border'>{importReport.errors.map((error) => <div key={`${error.row}-${error.error}`} className='grid grid-cols-[70px_1fr] gap-3 p-3 text-sm'><span className='font-medium'>Row {error.row}</span><span className='break-words text-muted-foreground'>{error.error}</span></div>)}</div> : <p className='rounded-md border bg-muted/30 p-4 text-sm'>Every imported row passed validation.</p>}</DialogContent></Dialog>
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}
      title='Delete inventory record?' desc='The API will reject deletion when another resource depends on this record.'
      destructive isLoading={remove.isPending} handleConfirm={() => deleting && remove.mutate(deleting)} />
  </Main></>
}

function InventoryDialog({ resource, record, systems, environments, credentials, defaultSystemId, open, onOpenChange }: {
  resource: Resource; record: InventoryRecord | null | undefined; systems: SystemRecord[];
  environments: EnvironmentRecord[]; credentials: CredentialRecord[]; defaultSystemId: string; open: boolean;
  onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient()
  const initial = record ? toForm(resource, record) : { ...emptyForms[resource],
    ...(resource === 'servers' || resource === 'credentials' ? { system_id: defaultSystemId } : {}),
    ...(resource === 'servers' && defaultSystemId ? {
      credential_id: systems.find((item) => item.id === defaultSystemId)?.default_credential_id ?? '',
    } : {}) }
  const [form, setForm] = useState<Record<string, unknown>>(initial)
  const key = `${resource}-${record?.id ?? 'new'}-${open}`
  const save = useMutation({ mutationFn: async () => {
    const payload = toPayload(resource, form, Boolean(record))
    return record ? apiClient.put(`/inventory/${resource}/${record.id}`, payload) :
      apiClient.post(`/inventory/${resource}`, payload)
  }, onSuccess: async () => { await client.invalidateQueries({ queryKey: ['inventory', resource] })
    onOpenChange(false); toast.success(record ? 'Record updated.' : 'Record created.') },
  onError: () => toast.error('Validation failed or the record already exists.') })
  const field = (name: string, label: string, type = 'text', required = true) => <div className='space-y-1'><Label htmlFor={name}>{label}</Label>
    <Input id={name} type={type} required={required} value={String(form[name] ?? '')}
      onChange={(e) => setForm({ ...form, [name]: type === 'number' ? Number(e.target.value) : e.target.value })} /></div>
  const selectedSystemId = String(form.system_id ?? '')
  const eligibleCredentials = credentials.filter((item) =>
    (item.system_id === null || item.system_id === selectedSystemId) && item.is_active)
  return <Dialog key={key} open={open} onOpenChange={onOpenChange}><DialogContent className='max-h-[90svh] overflow-auto sm:max-w-2xl'>
    <DialogHeader><DialogTitle>{record ? 'Edit' : 'Add'} {resource.slice(0, -1)}</DialogTitle>
      <DialogDescription>Changes are validated and persisted through the backend API.</DialogDescription></DialogHeader>
    <form id='inventory-form' className='grid gap-4' onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      {resource === 'systems' && <>{field('name', 'Name')}{field('code', 'Code')}{field('owner', 'Owner')}
        {field('criticality', 'Criticality')}<SelectField label='Default SSH credential (optional)' allowClear value={String(form.default_credential_id ?? '')}
          options={credentials.filter((item) => item.is_active && (!item.system_id || item.system_id === record?.id))
            .sort((left, right) => Number(Boolean(left.system_id)) - Number(Boolean(right.system_id)) || left.name.localeCompare(right.name))
            .map((item) => [item.id, `${item.name} - ${item.username} (${item.system_id ? 'System' : 'Global'})`])}
          onChange={(default_credential_id) => setForm({ ...form, default_credential_id })} />
        <p className='text-xs text-muted-foreground'>A new System can immediately use any active Global credential. System-scoped credentials become available after the System exists.</p>
        <TextField label='Description' value={String(form.description ?? '')}
          onChange={(value) => setForm({ ...form, description: value })} /></>}
      {resource === 'environments' && <>{field('name', 'Name')}{field('risk_weight', 'Risk weight', 'number')}
        <TextField label='Description' value={String(form.description ?? '')} onChange={(value) => setForm({ ...form, description: value })} /></>}
      {resource === 'credentials' && <><SelectField label='System scope (optional)' value={selectedSystemId} allowClear options={systems.map((x) => [x.id, `${x.code} - ${x.name}`])}
          onChange={(value) => setForm({ ...form, system_id: value })} />{field('name', 'Credential name')}{field('username', 'SSH username')}
        {field('password', record ? 'New password (leave blank to keep current)' : 'SSH password', 'password', !record)}
        <p className='rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground'>Leave System empty to create a global credential available to every System. The password is encrypted by the backend Secret Manager using AES-GCM and is never returned by the API or written to a workspace.</p></>}
      {resource === 'servers' && <>{field('hostname', 'Hostname')}{field('ip_address', 'IP address')}{field('os', 'Operating system')}
        {field('server_type', 'Server type')}{field('role', 'Role')}{field('tags', 'Tags, comma separated')}{field('port', 'SSH port', 'number')}
        <SelectField label='System' value={String(form.system_id ?? '')} options={systems.map((x) => [x.id, `${x.code} - ${x.name}`])}
          onChange={(value) => setForm({ ...form, system_id: value,
            credential_id: systems.find((item) => item.id === value)?.default_credential_id ?? '' })} />
        <SelectField label='Environment' value={String(form.environment_id ?? '')} options={environments.map((x) => [x.id, x.name])}
          onChange={(value) => setForm({ ...form, environment_id: value })} />
        <SelectField label='SSH credential' value={String(form.credential_id ?? '')} options={eligibleCredentials.map((x) => [x.id, `${x.name} - ${x.username} (${x.system_id ? 'System' : 'Global'})`])}
          onChange={(value) => setForm({ ...form, credential_id: value })} />
        <p className='rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground'>Create or update credentials in the SSH credentials tab. This server stores only the credential reference; passwords remain encrypted and are never returned to the browser.</p>
        <TextField label='Description' value={String(form.description ?? '')} onChange={(value) => setForm({ ...form, description: value })} /></>}
    </form><DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button>
      <Button form='inventory-form' type='submit' disabled={save.isPending}>Save</Button></DialogFooter>
  </DialogContent></Dialog>
}

function SystemDetailsDialog({ system, detail, loading, onOpenChange, onEditSystem, onAddServer, onEditServer, onDeleteServer }: {
  system?: SystemRecord; detail?: SystemDetail; loading: boolean; onOpenChange: (open: boolean) => void;
  onEditSystem: (item: SystemRecord) => void; onAddServer: (systemId: string) => void;
  onEditServer: (item: ServerRecord) => void; onDeleteServer: (item: ServerRecord) => void }) {
  const client = useQueryClient(); const uploadRef = useRef<HTMLInputElement>(null)
  const upload = useMutation({ mutationFn: async (file: File) => { if (!system) return; const form = new FormData()
    form.append('system_id', system.id); form.append('title', file.name.replace(/\.[^.]+$/, '')); form.append('file', file)
    return apiClient.post('/knowledge/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } }) },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['inventory', 'system-detail', system?.id] }); await client.invalidateQueries({ queryKey: ['knowledge'] }); toast.success('Knowledge uploaded to this System workspace.') },
    onError: () => toast.error('Knowledge upload failed. Use PDF, DOCX, Markdown or TXT up to 20 MB.') })
  const removeKnowledge = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/knowledge/${id}`),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['inventory', 'system-detail', system?.id] }); await client.invalidateQueries({ queryKey: ['knowledge'] }); toast.success('Knowledge document deleted.') },
    onError: () => toast.error('Knowledge document could not be deleted.') })
  return <Dialog open={Boolean(system)} onOpenChange={onOpenChange}><DialogContent className='grid max-h-[92svh] grid-rows-[auto_minmax(0,1fr)] overflow-hidden p-0 sm:max-w-6xl'>
    <DialogHeader className='border-b px-6 py-5 pe-14'><div className='flex flex-wrap items-start justify-between gap-3'><div><DialogTitle>{system?.name}</DialogTitle><DialogDescription>{system?.code} / complete System administration</DialogDescription></div>
      {system && <Button size='sm' variant='outline' onClick={() => onEditSystem(system)}><Pencil className='size-4' />Edit System</Button>}</div></DialogHeader>
    {loading || !detail ? <div className='grid min-h-80 place-items-center text-sm text-muted-foreground'>Loading System inventory...</div> : <Tabs defaultValue='overview' className='flex min-h-0 flex-col px-6 pt-4'>
      <TabsList className='w-full justify-start'><TabsTrigger value='overview'>Overview</TabsTrigger><TabsTrigger value='servers'>Servers ({detail.servers.length})</TabsTrigger><TabsTrigger value='knowledge'>Knowledge ({detail.knowledge.length})</TabsTrigger></TabsList>
      <TabsContent value='overview' className='min-h-0 flex-1 overflow-auto py-5'><dl className='grid gap-5 sm:grid-cols-2 lg:grid-cols-3'>
        {[['Code', detail.system.code], ['Name', detail.system.name], ['Owner', detail.system.owner || 'Unassigned'], ['Criticality', detail.system.criticality], ['Servers', String(detail.servers.length)], ['Knowledge files', String(detail.knowledge.length)]].map(([label, value]) => <div key={label}><dt className='text-xs text-muted-foreground'>{label}</dt><dd className='mt-1 break-words font-medium'>{value}</dd></div>)}</dl>
        <div className='mt-6 border-t pt-5'><p className='text-xs text-muted-foreground'>Description</p><p className='mt-2 whitespace-pre-wrap text-sm'>{detail.system.description || 'No description provided.'}</p></div></TabsContent>
      <TabsContent value='servers' className='min-h-0 flex-1 overflow-auto py-5'><div className='mb-3 flex items-center justify-between'><div><h3 className='font-medium'>System servers</h3><p className='text-xs text-muted-foreground'>Create, edit or remove server records without leaving this System context.</p></div><Button size='sm' onClick={() => onAddServer(detail.system.id)}><Plus className='size-4' />Add server</Button></div>
        <div className='divide-y rounded-md border'>{detail.servers.map((server) => <div key={server.id} className='grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 p-3'><div className='flex min-w-0 items-center gap-3'><ServerIcon className='size-4 shrink-0 text-muted-foreground' /><div className='min-w-0'><p className='truncate text-sm font-medium'>{server.hostname}</p><p className='truncate text-xs text-muted-foreground'>{server.ip_address} / {server.os} / {server.role || 'No role'} / SSH: {server.credential_username || 'not configured'}</p></div></div><div className='flex items-center gap-1'><StatusBadge value={server.status} /><Button title='Edit server' size='icon' variant='ghost' onClick={() => onEditServer(server)}><Pencil className='size-4' /></Button><Button title='Delete server' size='icon' variant='ghost' className='text-destructive' onClick={() => onDeleteServer(server)}><Trash2 className='size-4' /></Button></div></div>)}
          {!detail.servers.length && <p className='p-10 text-center text-sm text-muted-foreground'>No servers are registered in this System.</p>}</div></TabsContent>
      <TabsContent value='knowledge' className='min-h-0 flex-1 overflow-auto py-5'><input ref={uploadRef} type='file' accept='.pdf,.docx,.md,.txt' className='hidden' onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); event.target.value = '' }} />
        <div className='mb-3 flex items-center justify-between'><div><h3 className='font-medium'>System knowledge</h3><p className='text-xs text-muted-foreground'>Original files are retained in the System workspace and indexed for Codex.</p></div><Button size='sm' disabled={upload.isPending} onClick={() => uploadRef.current?.click()}><FileUp className='size-4' />Upload knowledge</Button></div>
        <div className='divide-y rounded-md border'>{detail.knowledge.map((item) => <div key={item.id} className='flex items-center gap-3 p-3'><div className='min-w-0 flex-1'><p className='truncate text-sm font-medium'>{item.title}</p><p className='text-xs text-muted-foreground'>{item.document_type} / {new Date(item.updated_at).toLocaleString()}</p></div><Button title='Delete knowledge' size='icon' variant='ghost' className='text-destructive' disabled={removeKnowledge.isPending} onClick={() => removeKnowledge.mutate(item.id)}><Trash2 className='size-4' /></Button></div>)}
          {!detail.knowledge.length && <p className='p-10 text-center text-sm text-muted-foreground'>No knowledge has been uploaded for this System.</p>}</div></TabsContent>
    </Tabs>}
  </DialogContent></Dialog>
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <div className='space-y-1'><Label>{label}</Label><Textarea value={value} onChange={(e) => onChange(e.target.value)} /></div>
}
function SelectField({ label, value, options, onChange, allowClear = false }: { label: string; value: string; options: string[][]; onChange: (value: string) => void; allowClear?: boolean }) {
  return <div className='space-y-1'><Label>{label}</Label><SearchableSelect ariaLabel={label} value={value} onValueChange={onChange}
    allowClear={allowClear} placeholder={allowClear ? 'Global / all Systems' : `Select ${label.toLowerCase()}`} searchPlaceholder={`Search ${label.toLowerCase()}...`}
    options={options.map(([id, name]) => ({ value: id, label: name }))} /></div>
}
function displayName(item: InventoryRecord) { return 'hostname' in item ? item.hostname : item.name }
function details(item: InventoryRecord) { if ('hostname' in item) return `${item.ip_address} · ${item.os}`
  if ('code' in item) return `${item.code} · ${item.owner}`; if ('risk_weight' in item) return `Risk ${item.risk_weight}`
  return item.provider }
function statusValue(item: InventoryRecord) { if ('status' in item) return item.status
  if ('is_active' in item) return item.is_active ? 'active' : 'inactive'; if ('criticality' in item) return item.criticality
  return 'configured' }
function inventoryColumns(resource: Resource, systems: SystemRecord[], environments: EnvironmentRecord[]): EnterpriseColumn<InventoryRecord>[] {
  if (resource === 'servers') return [
    { id: 'hostname', header: 'Hostname', accessor: (item) => (item as ServerRecord).hostname, cell: (item) => <Link className='font-medium hover:underline' to='/inventory/servers/$serverId' params={{ serverId: item.id }}>{(item as ServerRecord).hostname}</Link> },
    { id: 'ip', header: 'IP address', accessor: (item) => (item as ServerRecord).ip_address, size: 150 },
    { id: 'os', header: 'Operating system', accessor: (item) => (item as ServerRecord).os, size: 200 },
    { id: 'role', header: 'Role', accessor: (item) => (item as ServerRecord).role },
    { id: 'system', header: 'System', accessor: (item) => systems.find((value) => value.id === (item as ServerRecord).system_id)?.code ?? 'Unknown' },
    { id: 'environment', header: 'Environment', accessor: (item) => environments.find((value) => value.id === (item as ServerRecord).environment_id)?.name ?? 'Unknown' },
    { id: 'ssh-user', header: 'SSH user', accessor: (item) => (item as ServerRecord).credential_username || 'Not configured', size: 160 },
    { id: 'status', header: 'Status', accessor: statusValue, cell: (item) => <StatusBadge value={statusValue(item)} />, size: 120 },
  ]
  if (resource === 'credentials') return [
    { id: 'name', header: 'Credential', accessor: displayName, cell: (item) => <span className='font-medium'>{displayName(item)}</span> },
    { id: 'system', header: 'Scope', accessor: (item) => systems.find((value) => value.id === (item as CredentialRecord).system_id)?.code ?? 'Global',
      cell: (item) => (item as CredentialRecord).system_id ? systems.find((value) => value.id === (item as CredentialRecord).system_id)?.code ?? 'Unknown' : <StatusBadge value='global' /> },
    { id: 'username', header: 'SSH username', accessor: (item) => (item as CredentialRecord).username || 'Not available' },
    { id: 'security', header: 'Password', accessor: () => 'Encrypted', cell: () => <span className='text-xs text-muted-foreground'>Encrypted / hidden</span> },
    { id: 'status', header: 'Status', accessor: statusValue, cell: (item) => <StatusBadge value={statusValue(item)} />, size: 140 },
  ]
  return [
    { id: 'name', header: resource === 'systems' ? 'Name / code' : 'Name', accessor: displayName, cell: (item) => <span className='font-medium'>{displayName(item)}</span> },
    { id: 'details', header: 'Details', accessor: details, size: 280 },
    { id: 'status', header: 'Status', accessor: statusValue, cell: (item) => <StatusBadge value={statusValue(item)} />, size: 140 },
  ]
}
function toForm(resource: Resource, item: InventoryRecord): Record<string, unknown> { if (resource === 'credentials')
  return { name: displayName(item), system_id: (item as CredentialRecord).system_id ?? '', username: (item as CredentialRecord).username,
    password: '', is_active: (item as CredentialRecord).is_active }
  if (resource === 'servers') { const server = item as ServerRecord; return { ...server, tags: server.tags.join(', '),
    port: Number(server.ssh_config.port ?? 22), credential_id: server.credential_id ?? '' } }
  return { ...item, ...('code' in item ? { default_credential_id: (item as SystemRecord).default_credential_id ?? '' } : {}) } }
function toPayload(resource: Resource, form: Record<string, unknown>, editing: boolean) { if (resource === 'credentials') {
  const secret = form.password ? { username: form.username, password: form.password } : undefined
  const systemId = form.system_id || null
  return editing ? { name: form.name, system_id: systemId, username: form.username, metadata_json: {}, is_active: form.is_active, ...(secret ? { secret_payload: secret } : {}) } :
    { name: form.name, system_id: systemId, metadata_json: {}, secret_payload: secret } }
  if (resource === 'servers') return { hostname: form.hostname, ip_address: form.ip_address, os: form.os,
    server_type: form.server_type, role: form.role, description: form.description, system_id: form.system_id,
    environment_id: form.environment_id, credential_id: form.credential_id || null,
    tags: String(form.tags ?? '').split(',').map((x) => x.trim()).filter(Boolean), ssh_config: { port: Number(form.port) } }
  const { id, created_at, updated_at, ...payload } = form
  if (resource === 'systems') payload.default_credential_id = payload.default_credential_id || null
  void id; void created_at; void updated_at
  return payload }
