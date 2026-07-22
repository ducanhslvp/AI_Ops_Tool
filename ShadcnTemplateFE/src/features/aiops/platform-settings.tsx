import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { CheckCircle2, Loader2, Pencil, PlugZap, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ContentSection } from '@/features/settings/components/content-section'
import { StatusBadge } from './status-badge'

export type SettingsSection = 'ai-providers' | 'ssh-gateways' | 'plugins' | 'notifications' | 'settings' | 'report-templates'
interface ResourceRecord { id: string; name?: string; key?: string; enabled?: boolean; is_active?: boolean;
  provider_type?: string; model?: string; category?: string; version?: string; channel_type?: string;
  scope?: string; description?: string; config?: Record<string, unknown>; config_schema?: Record<string, unknown>;
  value?: Record<string, unknown>; capabilities?: string[]; secret_reference?: string | null;
  format?: string; template_body?: string; exclusive_mode?: boolean; health_status?: string;
  health_detail?: string | null; detected_version?: string | null }
interface ProviderHealth { provider: string; status: 'ready' | 'disconnected' | 'degraded' | 'authentication_required'; model?: string; version?: string; detail?: string }
const metadata = {
  'ai-providers': ['AI Providers', 'Provider configuration and active runtime selection.'],
  'ssh-gateways': ['SSH Gateways', 'Timeout, output and host-key policies persisted in the database.'],
  plugins: ['Plugins', 'Installed integration capability metadata.'],
  notifications: ['Notifications', 'Email, webhook, Slack, Teams and in-app channels.'],
  settings: ['Platform Settings', 'Database-backed platform and observability configuration.'],
  'report-templates': ['Report Templates', 'Reusable evidence-based report layouts.'],
} as const

export function PlatformSettingsPage({ section }: { section: SettingsSection }) {
  const client = useQueryClient(); const [query, setQuery] = useState(''); const [editing, setEditing] = useState<ResourceRecord | null | undefined>()
  const [deleting, setDeleting] = useState<ResourceRecord>()
  const [providerHealth, setProviderHealth] = useState<Record<string, ProviderHealth>>({})
  const recordsQuery = useQuery({ queryKey: ['admin', section], queryFn: async () =>
    (await apiClient.get<ResourceRecord[]>(`/admin/${section}`)).data })
  const records = useMemo(() => (recordsQuery.data ?? []).filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase())), [query, recordsQuery.data])
  const remove = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/admin/${section}/${id}`), onSuccess: async () => {
    setDeleting(undefined); await client.invalidateQueries({ queryKey: ['admin', section] }); toast.success('Configuration deleted.') },
    onError: () => toast.error('Configuration could not be deleted.') })
  const activate = useMutation({ mutationFn: async (id: string) => apiClient.post(`/admin/ai-providers/${id}/activate`), onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ['admin', section] }); toast.success('Codex CLI is now handling AI Chat.') }, onError: (error) => {
      const body = error instanceof AxiosError ? error.response?.data as { detail?: string } | undefined : undefined
      toast.error(body?.detail ?? 'Provider activation failed health or configuration checks.') } })
  const testConnection = useMutation({ mutationFn: async (item: ResourceRecord) => (await apiClient.post<ProviderHealth>(`/admin/ai-providers/${item.id}/test-connection`)).data,
    onSuccess: (health, item) => { setProviderHealth((current) => ({ ...current, [item.id]: health })); if (health.status === 'ready') toast.success(`Connected${health.version ? `: ${health.version}` : '.'}`); else toast.error(health.detail ?? `Provider is ${health.status}.`) },
    onError: (error, item) => { const body = error instanceof AxiosError ? error.response?.data as { detail?: string; error?: { message?: string } } | undefined : undefined
      const detail = body?.detail ?? body?.error?.message ?? 'Connection test failed.'
      setProviderHealth((current) => ({ ...current, [item.id]: { provider: item.provider_type ?? 'provider', status: 'disconnected', detail } })); toast.error(detail) } })
  return <ContentSection title={metadata[section][0]} desc={metadata[section][1]}>
    <div>{section === 'ai-providers' && <p className='mb-4 max-w-3xl text-sm text-muted-foreground'>AI Chat uses the active provider only. Codex CLI runs under the backend service account and reuses the selected System workspace without storing an API key.</p>}
    {section === 'ssh-gateways' && <p className='mb-4 max-w-3xl text-sm text-muted-foreground'>The active profile is loaded for each Terminal, Discovery and AI command request. Credentials remain isolated in Secret Manager.</p>}
    <div className='mb-4 flex flex-wrap items-center gap-2'><Input className='min-w-56 flex-1' value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search ${metadata[section][0].toLowerCase()}`} />
      <Button onClick={() => setEditing(null)}><Plus className='size-4' />Add {section === 'ai-providers' ? 'provider' : 'profile'}</Button></div>
    <div className='divide-y rounded-md border'>{records.map((item) => <div key={item.id} className='flex items-center gap-3 p-3'>
      <div className='min-w-0 flex-1'><p className='truncate text-sm font-medium'>{item.name ?? `${item.scope}/${item.key}`}</p>
        <p className='truncate text-xs text-muted-foreground'>{section === 'ai-providers' ? `${item.provider_type === 'codex' ? 'Codex CLI default model' : `${item.provider_type} / ${item.model}`}${item.exclusive_mode ? ' / exclusive' : ''}` : item.category ?? item.channel_type ?? item.description ?? 'Database setting'}</p>
        {section === 'ai-providers' && <p className='mt-1 truncate text-xs text-muted-foreground'>{providerHealth[item.id]?.detail ?? item.health_detail ?? item.detected_version ?? 'Connection has not been tested'}</p>}</div>
      <StatusBadge value={providerHealth[item.id]?.status ?? (item.health_status !== 'unknown' ? item.health_status : item.is_active ? 'active' : item.enabled === false ? 'disabled' : 'configured')} />
      {section === 'ai-providers' && <Button title='Test connection' aria-label={`Test connection ${item.name}`} size='sm' variant='outline' disabled={testConnection.isPending && testConnection.variables?.id === item.id} onClick={() => testConnection.mutate(item)}>{testConnection.isPending && testConnection.variables?.id === item.id ? <Loader2 className='size-4 animate-spin' /> : <PlugZap className='size-4' />}Test</Button>}
      {section === 'ai-providers' && !item.is_active && <Button title='Activate provider' size='sm' variant='outline' onClick={() => activate.mutate(item.id)}><CheckCircle2 className='size-4' />Activate</Button>}
      <Button title='Edit' size='icon' variant='ghost' onClick={() => setEditing(item)}><Pencil className='size-4' /></Button>
      <Button title='Delete' size='icon' variant='ghost' onClick={() => setDeleting(item)}><Trash2 className='size-4' /></Button>
    </div>)}{!records.length && <p className='p-6 text-center text-sm text-muted-foreground'>No configuration records.</p>}</div>
    <ResourceDialog key={`${section}-${editing?.id ?? 'new'}-${editing !== undefined}`} section={section} record={editing}
      open={editing !== undefined} onOpenChange={(open) => !open && setEditing(undefined)} />
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)} title='Delete configuration?'
      desc='Active or referenced records are protected by the backend.' destructive isLoading={remove.isPending}
      handleConfirm={() => deleting && remove.mutate(deleting.id)} />
    </div>
  </ContentSection>
}

function ResourceDialog({ section, record, open, onOpenChange }: { section: SettingsSection; record: ResourceRecord | null | undefined;
  open: boolean; onOpenChange: (open: boolean) => void }) {
  const client = useQueryClient(); const initial = toForm(section, record); const [form, setForm] = useState<Record<string, string | boolean>>(initial)
  const save = useMutation({ mutationFn: async () => { const payload = toPayload(section, form, record)
    return record?.id ? apiClient.put(`/admin/${section}/${record.id}`, payload) : apiClient.post(`/admin/${section}`, payload) },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['admin', section] }); onOpenChange(false); toast.success('Configuration saved.') },
    onError: () => toast.error('Configuration validation failed. Check JSON and unique fields.') })
  const input = (name: string, label: string, required = true) => <div className='space-y-1'><Label>{label}</Label><Input required={required} value={String(form[name] ?? '')}
    onChange={(e) => setForm({ ...form, [name]: e.target.value })} /></div>
  const isCodex = section === 'ai-providers' && form.provider_type === 'codex'
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className='max-h-[90svh] overflow-auto sm:max-w-2xl'><DialogHeader>
    <DialogTitle>{record?.id ? 'Edit' : 'Add'} {metadata[section][0]}</DialogTitle><DialogDescription>No inline provider or credential secrets are accepted.</DialogDescription></DialogHeader>
    <form id='resource-form' className='grid gap-3' onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      {section !== 'settings' && input('name', 'Name')}{section === 'settings' && <>{input('scope', 'Scope')}{input('key', 'Key')}</>}
      {section === 'ai-providers' && <><div className='space-y-1'><Label>Provider type</Label><select className='h-9 w-full rounded-md border bg-background px-3 text-sm' value={String(form.provider_type)} onChange={(event) => setForm({ ...form, provider_type: event.target.value })}><option value='codex'>Codex CLI</option><option value='openai'>OpenAI</option><option value='claude'>Claude</option><option value='gemini'>Gemini</option><option value='ollama'>Ollama</option><option value='lm_studio'>LM Studio</option><option value='mock'>Local test adapter</option></select></div>
        {isCodex ? <><div className='grid gap-3 sm:grid-cols-2'>{input('executable', 'CLI executable')}{input('timeout_seconds', 'Timeout (seconds)')}</div>
          <div className='space-y-3 border-y py-3'><ToggleRow label='Codex CLI only' description='Prevent fallback to another provider.' checked={Boolean(form.exclusive_mode)} onCheckedChange={(checked) => setForm({ ...form, exclusive_mode: checked })} /><ToggleRow label='Verify authentication' description='Validate the saved Codex login during connection tests.' checked={Boolean(form.verify_authentication)} onCheckedChange={(checked) => setForm({ ...form, verify_authentication: checked })} /></div>
          <details className='group'><summary className='cursor-pointer text-sm font-medium'>Advanced options</summary><div className='mt-3 grid gap-3 sm:grid-cols-2'>{input('profile', 'CLI profile', false)}{input('codex_home', 'CODEX_HOME', false)}{input('model', 'Default model', false)}{input('models', 'Selectable models', false)}</div></details>
          <p className='text-xs text-muted-foreground'>Save the provider, test the connection, then activate it. Use <code>codex</code> for automatic executable discovery or enter the absolute executable path.</p></> : <>{input('model', 'Model')}{input('secret_reference', 'Secret reference', false)}<p className='text-xs text-muted-foreground'>Hosted providers must reference Secret Manager; inline credentials are rejected.</p></>}</>}
      {section === 'plugins' && <>{input('category', 'Category')}{input('version', 'Version')}</>}
      {section === 'report-templates' && input('format', 'Format')}
      {section === 'notifications' && input('channel_type', 'Channel type')}
      {section !== 'ai-providers' && section !== 'notifications' && section !== 'plugins' && input('description', 'Description', false)}
      {section === 'ssh-gateways' && <><div className='grid gap-3 sm:grid-cols-2'>{input('connect_timeout_seconds', 'Connect timeout (seconds)')}{input('command_timeout_seconds', 'Command timeout (seconds)')}{input('output_limit_bytes', 'Output limit (bytes)')}{input('max_attempts', 'Maximum attempts')}{input('known_hosts_file', 'Known hosts file')}</div><div className='rounded-md border p-3'><ToggleRow label='Active runtime profile' description='Only one SSH Gateway profile can be active. Enabling this profile deactivates the previous one.' checked={Boolean(form.is_active)} onCheckedChange={(checked) => setForm({ ...form, is_active: checked })} /></div></>}
      {section === 'plugins' && input('capabilities', 'Capabilities, comma separated', false)}
      {section === 'report-templates' ? <div className='space-y-1'><Label>Template body</Label><Textarea className='min-h-48 font-mono'
        value={String(form.template_body ?? '')} onChange={(e) => setForm({ ...form, template_body: e.target.value })} /></div> :
        (!isCodex && section !== 'ssh-gateways' && <div className='space-y-1'><Label>{section === 'settings' ? 'Value JSON' : 'Configuration JSON'}</Label><Textarea className='min-h-36 font-mono'
          value={String(form.json ?? '{}')} onChange={(e) => setForm({ ...form, json: e.target.value })} /></div>)}
    </form><DialogFooter><Button variant='outline' onClick={() => onOpenChange(false)}>Cancel</Button><Button form='resource-form' type='submit' disabled={save.isPending}>Save</Button></DialogFooter>
  </DialogContent></Dialog>
}

function toForm(section: SettingsSection, item: ResourceRecord | null | undefined): Record<string, string | boolean> {
  if (!item) return { name: '', scope: 'platform', key: '', description: '', provider_type: 'codex', model: '', executable: 'codex', timeout_seconds: '120', profile: '', codex_home: '', exclusive_mode: true, verify_authentication: true,
    models: '', secret_reference: '', category: 'integration', version: '1.0.0', channel_type: 'in_app', capabilities: '',
    format: 'markdown', template_body: '# {system}\n\n{evidence}', connect_timeout_seconds: '10', command_timeout_seconds: '30', output_limit_bytes: '1048576', max_attempts: '2', known_hosts_file: '~/.ssh/known_hosts', is_active: true, json: '{}' }
  const jsonValue = section === 'settings' ? item.value : section === 'plugins' ? item.config_schema : item.config
  return { name: item.name ?? '', scope: item.scope ?? 'platform', key: item.key ?? '', description: item.description ?? '',
    provider_type: item.provider_type ?? 'mock', model: item.model ?? '', secret_reference: item.secret_reference ?? '',
    category: item.category ?? '', version: item.version ?? '1.0.0', channel_type: item.channel_type ?? 'in_app',
    capabilities: item.capabilities?.join(', ') ?? '', format: item.format ?? 'markdown', template_body: item.template_body ?? '',
    executable: String(item.config?.executable ?? 'codex'), timeout_seconds: String(item.config?.timeout_seconds ?? 120), profile: String(item.config?.profile ?? ''), codex_home: String(item.config?.codex_home ?? ''), models: Array.isArray(item.config?.models) ? item.config.models.join(', ') : '', exclusive_mode: item.exclusive_mode ?? false, verify_authentication: Boolean(item.config?.verify_authentication ?? true),
    connect_timeout_seconds: String(item.config?.connect_timeout_seconds ?? 10), command_timeout_seconds: String(item.config?.command_timeout_seconds ?? 30), output_limit_bytes: String(item.config?.output_limit_bytes ?? 1048576), max_attempts: String(item.config?.max_attempts ?? 2), known_hosts_file: String(item.config?.known_hosts_file ?? '~/.ssh/known_hosts'), is_active: item.is_active ?? true,
    json: JSON.stringify(jsonValue ?? {}, null, 2) }
}
function toPayload(section: SettingsSection, form: Record<string, string | boolean>, record: ResourceRecord | null | undefined) {
  if (section === 'report-templates') return { name: form.name, description: form.description, format: form.format,
    template_body: form.template_body, is_active: record?.is_active ?? true }
  const json = JSON.parse(String(form.json || '{}')) as Record<string, unknown>
  if (section === 'settings') return { scope: form.scope, key: form.key, description: form.description, value: json }
  if (section === 'ai-providers') { const codex = form.provider_type === 'codex'; return { name: form.name, provider_type: form.provider_type, model: form.model,
    secret_reference: codex ? null : form.secret_reference || null, config: codex ? { mode: 'cli', executable: form.executable || 'codex', timeout_seconds: Number(form.timeout_seconds || 120), profile: form.profile || undefined, codex_home: form.codex_home || undefined, models: String(form.models || '').split(',').map((item) => item.trim()).filter(Boolean), ephemeral: false, verify_authentication: Boolean(form.verify_authentication), max_output_bytes: 2000000 } : json, enabled: record?.enabled ?? true, is_active: record?.is_active ?? false, exclusive_mode: codex ? Boolean(form.exclusive_mode) : false } }
  if (section === 'plugins') return { name: form.name, category: form.category, version: form.version,
    capabilities: String(form.capabilities).split(',').map((x) => x.trim()).filter(Boolean), config_schema: json, enabled: record?.enabled ?? true }
  if (section === 'notifications') return { name: form.name, channel_type: form.channel_type, config: json, enabled: record?.enabled ?? true }
  if (section === 'ssh-gateways') return { name: form.name, description: form.description, is_active: Boolean(form.is_active), config: {
    connect_timeout_seconds: Number(form.connect_timeout_seconds), command_timeout_seconds: Number(form.command_timeout_seconds), output_limit_bytes: Number(form.output_limit_bytes), max_attempts: Number(form.max_attempts), known_hosts_file: form.known_hosts_file } }
  return { name: form.name, description: form.description, config: json, is_active: record?.is_active ?? true }
}

function ToggleRow({ label, description, checked, onCheckedChange }: { label: string; description: string; checked: boolean; onCheckedChange: (checked: boolean) => void }) {
  return <div className='flex items-center justify-between gap-4'><div><Label>{label}</Label><p className='text-xs text-muted-foreground'>{description}</p></div><Switch checked={checked} onCheckedChange={onCheckedChange} /></div>
}
