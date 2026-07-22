import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, TestTube2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { SearchableSelect } from '@/components/searchable-select'
import { ThemeSwitch } from '@/components/theme-switch'
import { EnterpriseDataTable, type EnterpriseColumn } from '@/components/enterprise-data-table'

interface Profile { id: string; name: string; description: string; is_active: boolean }
interface Tool { name: string; description: string; arguments_schema: Record<string, unknown> }
interface SimulatedCommand { id: string; action: string; os_name: string; arguments: Record<string, unknown>;
  profile_id: string; command: string; output: string; exit_code: number }

export function DevelopmentTestPage() {
  const client = useQueryClient(); const [profileDialog, setProfileDialog] = useState<Profile | null | undefined>()
  const [commandDialog, setCommandDialog] = useState<SimulatedCommand | null | undefined>(); const [profileId, setProfileId] = useState('')
  const status = useQuery({ queryKey: ['development', 'status'], retry: false, queryFn: async () =>
    (await apiClient.get<{ enabled: boolean; active_profile: string }>('/development/status')).data })
  const profiles = useQuery({ queryKey: ['development', 'profiles'], retry: false, queryFn: async () =>
    (await apiClient.get<Profile[]>('/development/profiles')).data })
  const tools = useQuery({ queryKey: ['tools'], queryFn: async () => (await apiClient.get<Tool[]>('/tools')).data })
  const selectedProfile = profileId || status.data?.active_profile || profiles.data?.[0]?.id || ''
  const commands = useQuery({ queryKey: ['development', 'commands', selectedProfile], enabled: Boolean(selectedProfile), queryFn: async () =>
    (await apiClient.get<SimulatedCommand[]>('/development/commands', { params: { profile_id: selectedProfile } })).data })
  const activate = useMutation({ mutationFn: async (id: string) => apiClient.put(`/development/profiles/${id}/active`), onSuccess: async (_, id) => {
    setProfileId(id); await client.invalidateQueries({ queryKey: ['development'] }); toast.success('Active test profile updated.') }, onError: () => toast.error('Profile could not be activated.') })
  const deleteProfile = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/development/profiles/${id}`), onSuccess: async () => {
    setProfileId(''); await client.invalidateQueries({ queryKey: ['development'] }); toast.success('Profile deleted.') }, onError: () => toast.error('Protected or referenced profile cannot be deleted.') })
  const deleteCommand = useMutation({ mutationFn: async (item: SimulatedCommand) => apiClient.delete(`/development/commands/${item.profile_id}/${item.id}`), onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ['development', 'commands'] }); toast.success('Simulated output deleted.') }, onError: () => toast.error('Command output could not be deleted.') })
  const bulkDeleteCommands = useMutation({ mutationFn: async (items: SimulatedCommand[]) => Promise.all(items.map((item) =>
    apiClient.delete(`/development/commands/${item.profile_id}/${item.id}`))), onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['development', 'commands'] }); toast.success('Selected command outputs deleted.')
    }, onError: () => toast.error('Some command outputs could not be deleted.') })
  if (status.isError) return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main><h1 className='text-2xl font-semibold'>Development Test Environment</h1>
    <p className='mt-2 text-sm text-muted-foreground'>This module is unavailable outside the guarded development environment.</p></Main></>
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main>
    <div className='mb-4'><h1 className='flex items-center gap-2 text-2xl font-semibold'><TestTube2 className='size-5' />Development Test Environment</h1>
      <p className='text-sm text-muted-foreground'>Backend-owned profiles and reviewed outputs for the production operation path.</p></div>
    <Tabs defaultValue='profiles'><TabsList><TabsTrigger value='profiles'>Profiles</TabsTrigger><TabsTrigger value='commands'>Command outputs</TabsTrigger></TabsList>
      <TabsContent value='profiles'><Card><CardHeader className='flex-row items-center justify-between'><CardTitle className='text-base'>Test Profiles</CardTitle>
        <Button size='sm' onClick={() => setProfileDialog(null)}><Plus className='size-4' />Add profile</Button></CardHeader><CardContent>
        <div className='divide-y'>{(profiles.data ?? []).map((profile) => <div key={profile.id} className='flex items-center gap-3 py-3'><div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'><p className='font-medium'>{profile.name}</p>{profile.is_active && <span className='text-xs text-emerald-600'>Active</span>}</div>
          <p className='text-sm text-muted-foreground'>{profile.description}</p></div>
          {!profile.is_active && <Button size='sm' variant='outline' onClick={() => activate.mutate(profile.id)}><Check className='size-4' />Activate</Button>}
          <Button title='Edit profile' size='icon' variant='ghost' onClick={() => setProfileDialog(profile)}><Pencil className='size-4' /></Button>
          <Button title='Delete profile' size='icon' variant='ghost' disabled={profile.id === 'healthy'} onClick={() => deleteProfile.mutate(profile.id)}><Trash2 className='size-4' /></Button>
        </div>)}</div></CardContent></Card></TabsContent>
      <TabsContent value='commands'><Card><CardHeader className='gap-3 sm:flex-row sm:items-center sm:justify-between'><div><CardTitle className='text-base'>Registered Command Outputs</CardTitle>
        <p className='text-sm text-muted-foreground'>Commands are rendered from registered Tool DSL actions.</p></div><div className='flex gap-2'><SearchableSelect ariaLabel='Command profile' value={selectedProfile} className='w-56'
          searchPlaceholder='Search test profiles...' options={(profiles.data ?? []).map((profile) => ({ value: profile.id, label: profile.name, keywords: profile.description }))} onValueChange={setProfileId} />
          <Button size='sm' onClick={() => setCommandDialog(null)}><Plus className='size-4' />Add output</Button></div></CardHeader><CardContent>
        <EnterpriseDataTable data={commands.data ?? []} columns={commandColumns} getRowId={(item) => `${item.profile_id}-${item.id}`} entityName='command'
          loading={commands.isLoading} searchPlaceholder='Search action, OS, or rendered command'
          rowActions={[{ label: 'Edit output', icon: Pencil, onSelect: setCommandDialog }, { label: 'Delete output', icon: Trash2, destructive: true, onSelect: (item) => deleteCommand.mutate(item) }]}
          bulkActions={[{ label: 'Delete selected', icon: Trash2, destructive: true, onSelect: (items) => bulkDeleteCommands.mutate(items) }]}
          emptyTitle='No command overrides' emptyDescription='This profile uses reviewed fallback snapshots. Add an override only when different evidence is required.' />
      </CardContent></Card></TabsContent></Tabs>
    <ProfileDialog record={profileDialog} open={profileDialog !== undefined} onOpenChange={(open) => !open && setProfileDialog(undefined)} />
    <CommandDialog record={commandDialog} profileId={selectedProfile} tools={tools.data ?? []} open={commandDialog !== undefined} onOpenChange={(open) => !open && setCommandDialog(undefined)} />
  </Main></>
}

const commandColumns: EnterpriseColumn<SimulatedCommand>[] = [
  { id: 'action', header: 'Action', accessor: (item) => item.action, cell: (item) => <code>{item.action}</code> },
  { id: 'command', header: 'Backend-rendered command', accessor: (item) => item.command, cell: (item) => <code className='text-xs'>{item.command}</code>, size: 360 },
  { id: 'os', header: 'Target OS', accessor: (item) => item.os_name, size: 180 },
  { id: 'exit', header: 'Exit code', accessor: (item) => item.exit_code, size: 100 },
]

function ProfileDialog({ record, open, onOpenChange }: { record: Profile | null | undefined; open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient(); const [id, setId] = useState(record?.id ?? ''); const [name, setName] = useState(record?.name ?? ''); const [description, setDescription] = useState(record?.description ?? '')
  const save = useMutation({ mutationFn: async () => apiClient.put(`/development/profiles/${id}`, { id, name, description }), onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ['development'] }); onOpenChange(false); toast.success('Profile saved.') }, onError: () => toast.error('Profile validation failed.') })
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>{record ? 'Edit' : 'Add'} test profile</DialogTitle><DialogDescription>Profiles select reviewed output without changing the Tool Registry.</DialogDescription></DialogHeader>
    <form id='profile-form' className='space-y-3' onSubmit={(e) => { e.preventDefault(); save.mutate() }}><div className='space-y-1'><Label>Identifier</Label><Input required pattern='[a-z0-9_]+' disabled={Boolean(record)} value={id} onChange={(e) => setId(e.target.value)} /></div>
      <div className='space-y-1'><Label>Name</Label><Input required value={name} onChange={(e) => setName(e.target.value)} /></div><div className='space-y-1'><Label>Description</Label><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></div></form>
    <DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='profile-form' type='submit' disabled={save.isPending}>Save</Button></DialogFooter></DialogContent></Dialog>
}

function CommandDialog({ record, profileId, tools, open, onOpenChange }: { record: SimulatedCommand | null | undefined; profileId: string; tools: Tool[]; open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient(); const [id, setId] = useState(record?.id ?? ''); const [action, setAction] = useState(record?.action ?? tools[0]?.name ?? '')
  const [osName, setOsName] = useState(record?.os_name ?? 'Ubuntu 24.04'); const [argumentsText, setArgumentsText] = useState(JSON.stringify(record?.arguments ?? {}, null, 2)); const [output, setOutput] = useState(record?.output ?? ''); const [exitCode, setExitCode] = useState(record?.exit_code ?? 0)
  const save = useMutation({ mutationFn: async () => apiClient.put(`/development/commands/${id}`, { id, action, os_name: osName, arguments: JSON.parse(argumentsText), profile_id: profileId, output, exit_code: exitCode }), onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ['development', 'commands'] }); onOpenChange(false); toast.success('Reviewed command output saved.') }, onError: () => toast.error('Use a registered action and valid JSON arguments.') })
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className='max-h-[85svh] overflow-auto'><DialogHeader><DialogTitle>{record ? 'Edit' : 'Add'} command output</DialogTitle><DialogDescription>The backend renders the command. Shell text cannot be submitted.</DialogDescription></DialogHeader>
    <form id='command-form' className='space-y-3' onSubmit={(e) => { e.preventDefault(); save.mutate() }}><div className='grid grid-cols-2 gap-3'><div className='space-y-1'><Label>Snapshot key</Label><Input required pattern='[a-z0-9_]+' disabled={Boolean(record)} value={id} onChange={(e) => setId(e.target.value)} /></div>
      <div className='space-y-1'><Label>Action</Label><SearchableSelect ariaLabel='Command action' value={action} searchPlaceholder='Search registered actions...'
        options={tools.map((tool) => ({ value: tool.name, label: tool.name, keywords: tool.description }))} onValueChange={setAction} /></div></div>
      <div className='space-y-1'><Label>Target OS</Label><Input required value={osName} onChange={(e) => setOsName(e.target.value)} /></div><div className='space-y-1'><Label>Validated arguments (JSON)</Label><Textarea className='font-mono' value={argumentsText} onChange={(e) => setArgumentsText(e.target.value)} /></div>
      <div className='space-y-1'><Label>Reviewed output</Label><Textarea required className='min-h-48 font-mono' value={output} onChange={(e) => setOutput(e.target.value)} /></div><div className='space-y-1'><Label>Exit code</Label><Input type='number' min={0} max={255} value={exitCode} onChange={(e) => setExitCode(Number(e.target.value))} /></div></form>
    <DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='command-form' type='submit' disabled={save.isPending}>Save output</Button></DialogFooter></DialogContent></Dialog>
}
