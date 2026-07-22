import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SearchableSelect } from '@/components/searchable-select'
import { ThemeSwitch } from '@/components/theme-switch'
import { StatusBadge } from './status-badge'

type Kind = 'users' | 'roles' | 'permissions'
interface Permission { id: string; code: string; description: string }
interface Role { id: string; name: string; description: string; permission_ids: string[] }
interface UserRecord { id: string; email: string; full_name: string; role_id: string; role_name: string; is_active: boolean }
type RecordType = Permission | Role | UserRecord
const kindLabels: Record<Kind, string> = { users: 'user', roles: 'role', permissions: 'permission' }

export function UserAdminPage() {
  const client = useQueryClient(); const [kind, setKind] = useState<Kind>('users')
  const [editing, setEditing] = useState<RecordType | null | undefined>(); const [deleting, setDeleting] = useState<RecordType>()
  const usersQuery = useQuery({ queryKey: ['admin', 'users'], queryFn: async () => (await apiClient.get<UserRecord[]>('/admin/users', { params: { page: 1, page_size: 200 } })).data })
  const rolesQuery = useQuery({ queryKey: ['admin', 'roles'], queryFn: async () => (await apiClient.get<Role[]>('/admin/roles', { params: { page: 1, page_size: 200 } })).data })
  const permissionsQuery = useQuery({ queryKey: ['admin', 'permissions'], queryFn: async () => (await apiClient.get<Permission[]>('/admin/permissions', { params: { page: 1, page_size: 200 } })).data })
  const records: RecordType[] = { users: usersQuery.data ?? [], roles: rolesQuery.data ?? [], permissions: permissionsQuery.data ?? [] }[kind]
  const remove = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/admin/${kind}/${id}`), onSuccess: async () => {
    setDeleting(undefined); await client.invalidateQueries({ queryKey: ['admin', kind] }); toast.success('Access record deleted.') },
    onError: () => toast.error('This record is protected or still referenced.') })
  const bulkRemove = useMutation({ mutationFn: async (items: RecordType[]) => Promise.all(items.map((item) => apiClient.delete(`/admin/${kind}/${item.id}`))),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['admin', kind] }); toast.success('Selected access records deleted.') },
    onError: () => toast.error('Some selected records are protected or still referenced.') })
  const exportRecords = (items: RecordType[] = records) => { const body = items.map((item) => JSON.stringify(item)).join('\n'); const url = URL.createObjectURL(new Blob([body], { type: 'application/x-ndjson' }))
    const link = document.createElement('a'); link.href = url; link.download = `${kind}.ndjson`; link.click(); URL.revokeObjectURL(url) }
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main><div className='mb-4 flex flex-wrap items-center justify-between gap-3'><div>
    <h1 className='text-2xl font-semibold tracking-tight'>Users & RBAC</h1><p className='text-sm text-muted-foreground'>Database-backed users, roles and permissions.</p></div>
    <div className='flex gap-2'><Button variant='outline' size='sm' onClick={() => exportRecords()}><Download className='size-4' />Export</Button>
      <Button size='sm' onClick={() => setEditing(null)}><Plus className='size-4' />Add {kindLabels[kind]}</Button></div></div>
    <Tabs value={kind} onValueChange={(value) => setKind(value as Kind)}><TabsList><TabsTrigger value='users'>Users</TabsTrigger>
      <TabsTrigger value='roles'>Roles</TabsTrigger><TabsTrigger value='permissions'>Permissions</TabsTrigger></TabsList></Tabs>
    <div className='mt-4'><EnterpriseDataTable data={records} columns={accessColumns(kind)} getRowId={(item) => item.id}
      loading={usersQuery.isLoading || rolesQuery.isLoading || permissionsQuery.isLoading} searchPlaceholder={`Search ${kind}`}
      entityName={kindLabels[kind]} rowActions={[{ label: 'Edit', icon: Pencil, onSelect: setEditing }, { label: 'Delete', icon: Trash2, destructive: true, onSelect: setDeleting }]}
      bulkActions={[{ label: 'Export selected', icon: Download, onSelect: exportRecords }, { label: 'Delete selected', icon: Trash2, destructive: true, onSelect: (items) => bulkRemove.mutate(items) }]}
      emptyTitle={`No ${kind} found`} emptyDescription='Adjust the search or create a new access record.' /></div>
    <AccessDialog key={`${kind}-${editing?.id ?? 'new'}-${editing !== undefined}`} kind={kind} record={editing} roles={rolesQuery.data ?? []}
      permissions={permissionsQuery.data ?? []} open={editing !== undefined} onOpenChange={(open) => !open && setEditing(undefined)} />
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)} title={`Delete ${kindLabels[kind]}?`}
      desc='Self-deletion and referenced access records are rejected by the API.' destructive isLoading={remove.isPending}
      handleConfirm={() => deleting && remove.mutate(deleting.id)} />
  </Main></>
}

function accessColumns(kind: Kind): EnterpriseColumn<RecordType>[] {
  if (kind === 'users') return [
    { id: 'email', header: 'Email', accessor: (item) => (item as UserRecord).email, cell: (item) => <span className='font-medium'>{(item as UserRecord).email}</span>, size: 260 },
    { id: 'name', header: 'Full name', accessor: (item) => (item as UserRecord).full_name, size: 220 },
    { id: 'role', header: 'Role', accessor: (item) => (item as UserRecord).role_name, size: 180 },
    { id: 'status', header: 'Status', accessor: (item) => (item as UserRecord).is_active ? 'active' : 'inactive', cell: (item) => <StatusBadge value={(item as UserRecord).is_active ? 'active' : 'inactive'} />, size: 130 },
  ]
  if (kind === 'roles') return [
    { id: 'name', header: 'Role', accessor: (item) => (item as Role).name, cell: (item) => <span className='font-medium'>{(item as Role).name}</span>, size: 220 },
    { id: 'description', header: 'Description', accessor: (item) => (item as Role).description, size: 420 },
    { id: 'permissions', header: 'Permissions', accessor: (item) => (item as Role).permission_ids.length, cell: (item) => `${(item as Role).permission_ids.length} permissions`, size: 150 },
  ]
  return [
    { id: 'code', header: 'Permission', accessor: (item) => (item as Permission).code, cell: (item) => <span className='font-mono text-sm font-medium'>{(item as Permission).code}</span>, size: 280 },
    { id: 'description', header: 'Description', accessor: (item) => (item as Permission).description, size: 520 },
  ]
}

function AccessDialog({ kind, record, roles, permissions, open, onOpenChange }: { kind: Kind; record: RecordType | null | undefined;
  roles: Role[]; permissions: Permission[]; open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient(); const [form, setForm] = useState<Record<string, string | boolean | string[]>>(toForm(kind, record))
  const save = useMutation({ mutationFn: async () => { const payload = toPayload(kind, form, record)
    return record ? apiClient.put(`/admin/${kind}/${record.id}`, payload) : apiClient.post(`/admin/${kind}`, payload) },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['admin', kind] }); onOpenChange(false); toast.success('Access record saved.') },
    onError: () => toast.error('Validation failed or a unique value already exists.') })
  const field = (name: string, label: string, type = 'text', required = true) => <div className='space-y-1'><Label>{label}</Label>
    <Input type={type} required={required} value={String(form[name] ?? '')} onChange={(e) => setForm({ ...form, [name]: e.target.value })} /></div>
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>
    {record ? 'Edit' : 'Add'} {kindLabels[kind]}</DialogTitle><DialogDescription>All access changes are validated by the administration API.</DialogDescription></DialogHeader>
    <form id='access-form' className='space-y-3' onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      {kind === 'users' && <>{field('email', 'Email', 'email')}{field('full_name', 'Full name')}{field('password', record ? 'New password (optional)' : 'Password', 'password', !record)}
        <div className='space-y-1'><Label>Role</Label><SearchableSelect ariaLabel='User role' value={String(form.role_id)} placeholder='Select role'
          searchPlaceholder='Search roles...' options={roles.map((role) => ({ value: role.id, label: role.name, keywords: role.description }))}
          onValueChange={(value) => setForm({ ...form, role_id: value })} /></div>
        <label className='flex items-center gap-2 text-sm'><Checkbox checked={Boolean(form.is_active)} onCheckedChange={(value) => setForm({ ...form, is_active: Boolean(value) })} />Active</label></>}
      {kind === 'roles' && <>{field('name', 'Name')}{field('description', 'Description', 'text', false)}<div className='space-y-2'><Label>Permissions</Label>
        <div className='grid max-h-56 grid-cols-2 gap-2 overflow-auto rounded-md border p-3'>{permissions.map((permission) => <label key={permission.id} className='flex items-center gap-2 text-sm'>
          <Checkbox checked={(form.permission_ids as string[]).includes(permission.id)} onCheckedChange={(value) => { const ids = form.permission_ids as string[]
            setForm({ ...form, permission_ids: value ? [...ids, permission.id] : ids.filter((id) => id !== permission.id) }) }} />{permission.code}</label>)}</div></div></>}
      {kind === 'permissions' && <>{field('code', 'Permission code')}{field('description', 'Description', 'text', false)}</>}
    </form><DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='access-form' type='submit' disabled={save.isPending}>Save</Button></DialogFooter>
  </DialogContent></Dialog>
}

function toForm(kind: Kind, record: RecordType | null | undefined): Record<string, string | boolean | string[]> {
  if (!record) return kind === 'users' ? { email: '', full_name: '', password: '', role_id: '', is_active: true } :
    kind === 'roles' ? { name: '', description: '', permission_ids: [] } : { code: '', description: '' }
  if (kind === 'users') { const user = record as UserRecord; return { email: user.email, full_name: user.full_name, password: '', role_id: user.role_id, is_active: user.is_active } }
  if (kind === 'roles') { const role = record as Role; return { name: role.name, description: role.description, permission_ids: role.permission_ids } }
  const permission = record as Permission; return { code: permission.code, description: permission.description }
}
function toPayload(kind: Kind, form: Record<string, string | boolean | string[]>, record: RecordType | null | undefined) {
  if (kind === 'users') return { email: form.email, full_name: form.full_name, role_id: form.role_id, is_active: form.is_active, ...(form.password ? { password: form.password } : {}) }
  if (kind === 'roles') return { name: form.name, description: form.description, permission_ids: form.permission_ids }
  void record; return { code: form.code, description: form.description }
}
