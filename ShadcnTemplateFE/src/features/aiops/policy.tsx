import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Download, Pencil, Plus, Power, PowerOff, ShieldCheck, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from './status-badge'

interface PolicyRule { id: string; name: string; description: string; effect: string; priority: number;
  role: string | null; environment: string | null; server_type: string | null; action: string | null;
  risk_level: string | null; time_window: Record<string, unknown>; is_active: boolean }
interface ToolRecord { name: string; plugin: string; description: string; risk_level: string; target_types: string[] }
interface Approval { id: string; action: string; reason: string; impact: string; status: string;
  server_id: string | null; created_at: string }
const emptyRule = { name: '', description: '', effect: 'allow', priority: 100, role: '', environment: '',
  server_type: '', action: '', risk_level: 'low', is_active: true }

export function PolicyPage() {
  const client = useQueryClient()
  const [effect, setEffect] = useState('')
  const [editing, setEditing] = useState<PolicyRule | null | undefined>()
  const [deleting, setDeleting] = useState<PolicyRule>()
  const [editingTool, setEditingTool] = useState<ToolRecord>()
  const [deletingTool, setDeletingTool] = useState<ToolRecord>()
  const rulesQuery = useQuery({ queryKey: ['policy', 'rules'], queryFn: async () =>
    (await apiClient.get<PolicyRule[]>('/policy/rules', { params: { page: 1, page_size: 200 } })).data })
  const toolsQuery = useQuery({ queryKey: ['tools'], queryFn: async () =>
    (await apiClient.get<ToolRecord[]>('/tools')).data })
  const approvalsQuery = useQuery({ queryKey: ['policy', 'approvals'], queryFn: async () =>
    (await apiClient.get<Approval[]>('/policy/approvals', { params: { page: 1, page_size: 200 } })).data })
  const rules = (rulesQuery.data ?? []).filter((rule) => !effect || rule.effect === effect)
  const remove = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/policy/rules/${id}`),
    onSuccess: async () => { setDeleting(undefined); await client.invalidateQueries({ queryKey: ['policy', 'rules'] }); toast.success('Policy deleted.') },
    onError: () => toast.error('Policy could not be deleted.') })
  const duplicate = useMutation({ mutationFn: async (id: string) => apiClient.post(`/policy/rules/${id}/duplicate`),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['policy', 'rules'] }); toast.success('Disabled policy copy created.') },
    onError: () => toast.error('Policy could not be duplicated.') })
  const setStatus = useMutation({ mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) =>
    apiClient.patch(`/policy/rules/${id}/status`, { is_active }), onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['policy', 'rules'] }); toast.success('Policy status updated.')
    }, onError: () => toast.error('Policy status could not be updated.') })
  const bulkDelete = useMutation({ mutationFn: async (items: PolicyRule[]) => apiClient.post('/policy/rules/actions/bulk-delete', { ids: items.map((item) => item.id) }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['policy', 'rules'] }); toast.success('Selected policies deleted.') },
    onError: () => toast.error('Selected policies could not be deleted atomically.') })
  const decide = useMutation({ mutationFn: async ({ id, decision }: { id: string; decision: string }) =>
    apiClient.post(`/policy/approvals/${id}/decision`, { decision, comment: `${decision} from policy console` }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['policy', 'approvals'] }); toast.success('Approval decision saved.') },
    onError: () => toast.error('Approval decision was rejected.') })
  const removeTool = useMutation({ mutationFn: async (name: string) => apiClient.delete(`/tools/${name}`),
    onSuccess: async () => { setDeletingTool(undefined); await client.invalidateQueries({ queryKey: ['tools'] }); toast.success('Tool disabled and removed from the registry.') },
    onError: () => toast.error('Tool could not be removed.') })
  const exportRules = (records: PolicyRule[] = rules) => { const csv = ['name,effect,priority,environment,action', ...records.map((rule) =>
    [rule.name, rule.effect, rule.priority, rule.environment ?? '', rule.action ?? ''].join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); const link = document.createElement('a')
    link.href = url; link.download = 'policies.csv'; link.click(); URL.revokeObjectURL(url) }
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4 flex flex-wrap items-center justify-between gap-3'><div><h1 className='text-2xl font-semibold tracking-tight'>Policy & Tool Registry</h1>
      <p className='text-sm text-muted-foreground'>Manage policy and human approvals through the API.</p></div>
      <div className='flex gap-2'><Button size='sm' variant='outline' onClick={() => exportRules()}><Download className='size-4' />Export</Button>
        <Button size='sm' onClick={() => setEditing(null)}><Plus className='size-4' />Add policy</Button></div></div>
    <Tabs defaultValue='rules'><TabsList><TabsTrigger value='rules'>Rules</TabsTrigger><TabsTrigger value='approvals'>Approvals</TabsTrigger>
      <TabsTrigger value='tools'>Tools</TabsTrigger></TabsList>
      <TabsContent value='rules'><Card><CardHeader><div className='flex flex-wrap items-center justify-between gap-3'><CardTitle className='text-base'>Policy Rules</CardTitle>
        </div></CardHeader>
        <CardContent><EnterpriseDataTable data={rules} columns={policyColumns} getRowId={(rule) => rule.id} entityName='policy rule' loading={rulesQuery.isLoading}
          searchPlaceholder='Search loaded policies' filterSlot={<select aria-label='Policy effect' value={effect} onChange={(e) => setEffect(e.target.value)} className='h-9 rounded-md border bg-background px-3 text-sm'>
            <option value=''>All effects</option><option value='allow'>Allow</option><option value='deny'>Deny</option><option value='approval_required'>Approval required</option></select>}
          rowActions={[{ label: 'Edit', icon: Pencil, onSelect: setEditing }, { label: 'Duplicate', icon: Copy, onSelect: (rule) => duplicate.mutate(rule.id) },
            { label: 'Enable', icon: Power, hidden: (rule) => rule.is_active, onSelect: (rule) => setStatus.mutate({ id: rule.id, is_active: true }) },
            { label: 'Disable', icon: PowerOff, hidden: (rule) => !rule.is_active, onSelect: (rule) => setStatus.mutate({ id: rule.id, is_active: false }) },
            { label: 'Delete', icon: Trash2, destructive: true, onSelect: setDeleting }]}
          bulkActions={[{ label: 'Export selected', icon: Download, onSelect: exportRules }, { label: 'Delete selected', icon: Trash2, destructive: true, onSelect: (items) => bulkDelete.mutate(items) }]} />
        </CardContent></Card></TabsContent>
      <TabsContent value='approvals'><Card><CardHeader><CardTitle className='text-base'>Pending and Recent Approvals</CardTitle></CardHeader><CardContent>
        <EnterpriseDataTable data={approvalsQuery.data ?? []} columns={approvalColumns} getRowId={(item) => item.id} entityName='approval' loading={approvalsQuery.isLoading}
          rowActions={[{ label: 'Approve', icon: Power, hidden: (item) => item.status !== 'pending', onSelect: (item) => decide.mutate({ id: item.id, decision: 'approved' }) },
            { label: 'Reject', icon: PowerOff, destructive: true, hidden: (item) => item.status !== 'pending', onSelect: (item) => decide.mutate({ id: item.id, decision: 'rejected' }) }]} />
      </CardContent></Card></TabsContent>
      <TabsContent value='tools'><Card><CardHeader><CardTitle className='flex items-center gap-2 text-base'><ShieldCheck className='size-4' />Registered Tools</CardTitle></CardHeader>
        <CardContent><EnterpriseDataTable data={toolsQuery.data ?? []} columns={toolColumns} getRowId={(tool) => tool.name} entityName='tool' loading={toolsQuery.isLoading}
          searchPlaceholder='Search registered tools' rowActions={[
            { label: 'Edit', icon: Pencil, onSelect: setEditingTool },
            { label: 'Delete', icon: Trash2, destructive: true, onSelect: setDeletingTool },
          ]} /></CardContent></Card></TabsContent>
    </Tabs>
    <PolicyDialog key={`${editing?.id ?? 'new'}-${editing !== undefined}`} record={editing} open={editing !== undefined}
      onOpenChange={(open) => !open && setEditing(undefined)} />
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)} title='Delete policy rule?'
      desc='Policy evaluation changes immediately after deletion.' destructive isLoading={remove.isPending}
      handleConfirm={() => deleting && remove.mutate(deleting.id)} />
    <ToolDialog key={editingTool?.name} record={editingTool} open={Boolean(editingTool)} onOpenChange={(open) => !open && setEditingTool(undefined)} />
    <ConfirmDialog open={Boolean(deletingTool)} onOpenChange={(open) => !open && setDeletingTool(undefined)} title='Remove registered tool?'
      desc='The tool will be disabled for users, direct execution and AI tool calling. Its backend command template remains protected.' destructive isLoading={removeTool.isPending}
      handleConfirm={() => deletingTool && removeTool.mutate(deletingTool.name)} />
  </Main></>
}

function ToolDialog({ record, open, onOpenChange }: { record?: ToolRecord; open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient()
  const [description, setDescription] = useState(record?.description ?? '')
  const [riskLevel, setRiskLevel] = useState(record?.risk_level ?? 'low')
  const [targetTypes, setTargetTypes] = useState(record?.target_types.join(', ') ?? '')
  const save = useMutation({ mutationFn: async () => apiClient.put(`/tools/${record?.name}`, {
    description, risk_level: riskLevel, target_types: targetTypes.split(',').map((item) => item.trim()).filter(Boolean),
  }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['tools'] }); onOpenChange(false); toast.success('Tool configuration updated.') },
  onError: () => toast.error('Tool configuration could not be updated.') })
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Edit registered tool</DialogTitle>
    <DialogDescription>Command templates remain immutable. Only policy-facing metadata can be changed.</DialogDescription></DialogHeader>
    <form id='tool-form' className='space-y-4' onSubmit={(event) => { event.preventDefault(); save.mutate() }}>
      <div className='space-y-1'><Label>Action</Label><Input value={record?.name ?? ''} disabled /></div>
      <div className='space-y-1'><Label>Description</Label><Textarea required minLength={3} value={description} onChange={(event) => setDescription(event.target.value)} /></div>
      <div className='space-y-1'><Label>Risk level</Label><select className='h-9 w-full rounded-md border bg-background px-3 text-sm' value={riskLevel} onChange={(event) => setRiskLevel(event.target.value)}>
        {['low', 'medium', 'high', 'critical'].map((level) => <option key={level} value={level}>{level}</option>)}</select></div>
      <div className='space-y-1'><Label>Target types</Label><Input required value={targetTypes} onChange={(event) => setTargetTypes(event.target.value)} placeholder='linux, windows, docker' />
        <p className='text-xs text-muted-foreground'>Comma-separated target adapters allowed to use this action.</p></div>
    </form><DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='tool-form' type='submit' disabled={save.isPending}>Save</Button></DialogFooter>
  </DialogContent></Dialog>
}

function PolicyDialog({ record, open, onOpenChange }: { record: PolicyRule | null | undefined; open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient(); const [form, setForm] = useState<Record<string, string | number | boolean>>(record ? {
    ...record, role: record.role ?? '', environment: record.environment ?? '', server_type: record.server_type ?? '',
    action: record.action ?? '', risk_level: record.risk_level ?? 'low' } : emptyRule)
  const save = useMutation({ mutationFn: async () => { const payload = { ...form, priority: Number(form.priority), time_window: {},
    role: form.role || null, environment: form.environment || null, server_type: form.server_type || null,
    action: form.action || null, risk_level: form.risk_level || null }
    return record ? apiClient.put(`/policy/rules/${record.id}`, payload) : apiClient.post('/policy/rules', payload) },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['policy', 'rules'] }); onOpenChange(false); toast.success('Policy saved.') },
    onError: () => toast.error('Policy validation failed.') })
  const input = (name: string, label: string, type = 'text') => <div className='space-y-1'><Label>{label}</Label><Input required={['name', 'effect'].includes(name)}
    type={type} value={String(form[name] ?? '')} onChange={(e) => setForm({ ...form, [name]: type === 'number' ? Number(e.target.value) : e.target.value })} /></div>
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>{record ? 'Edit' : 'Create'} policy rule</DialogTitle>
    <DialogDescription>Empty scope fields apply globally.</DialogDescription></DialogHeader><form id='policy-form' className='grid grid-cols-2 gap-3'
      onSubmit={(e) => { e.preventDefault(); save.mutate() }}>{input('name', 'Name')}{input('priority', 'Priority', 'number')}{input('effect', 'Effect')}
      {input('risk_level', 'Risk level')}{input('role', 'Role')}{input('environment', 'Environment')}{input('server_type', 'Server type')}{input('action', 'Action')}
      <div className='col-span-2 space-y-1'><Label>Description</Label><Textarea value={String(form.description)} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
    </form><DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='policy-form' type='submit'>Save</Button></DialogFooter></DialogContent></Dialog>
}

const policyColumns: EnterpriseColumn<PolicyRule>[] = [
  { id: 'name', header: 'Name', accessor: (rule) => rule.name, cell: (rule) => <div><p className='font-medium'>{rule.name}</p><p className='truncate text-xs text-muted-foreground'>{rule.description}</p></div>, size: 280 },
  { id: 'scope', header: 'Scope', accessor: (rule) => [rule.environment, rule.server_type, rule.action].filter(Boolean).join(' / ') || 'Global', size: 240 },
  { id: 'effect', header: 'Effect', accessor: (rule) => rule.effect, cell: (rule) => <StatusBadge value={rule.effect} /> },
  { id: 'priority', header: 'Priority', accessor: (rule) => rule.priority, size: 100 },
  { id: 'status', header: 'Status', accessor: (rule) => rule.is_active ? 'active' : 'disabled', cell: (rule) => <StatusBadge value={rule.is_active ? 'active' : 'disabled'} /> },
]
const approvalColumns: EnterpriseColumn<Approval>[] = [
  { id: 'action', header: 'Action', accessor: (item) => item.action, cell: (item) => <code>{item.action}</code> },
  { id: 'reason', header: 'Reason', accessor: (item) => item.reason, size: 260 },
  { id: 'impact', header: 'Impact', accessor: (item) => item.impact, size: 240 },
  { id: 'status', header: 'Status', accessor: (item) => item.status, cell: (item) => <StatusBadge value={item.status} /> },
]
const toolColumns: EnterpriseColumn<ToolRecord>[] = [
  { id: 'name', header: 'Action', accessor: (tool) => tool.name, cell: (tool) => <code>{tool.name}</code>, size: 220 },
  { id: 'plugin', header: 'Plugin', accessor: (tool) => tool.plugin },
  { id: 'description', header: 'Description', accessor: (tool) => tool.description, size: 300 },
  { id: 'risk', header: 'Risk', accessor: (tool) => tool.risk_level, cell: (tool) => <StatusBadge value={tool.risk_level} /> },
  { id: 'targets', header: 'Targets', accessor: (tool) => tool.target_types.join(', '), size: 260 },
]
