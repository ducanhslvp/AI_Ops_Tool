import { useMemo, useState } from 'react'
import { Check, MonitorCog, Network, Server } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'
import { SearchableSelect } from '@/components/searchable-select'
import { StatusBadge } from '@/features/aiops/status-badge'

export interface TargetSystem { id: string; code: string; name: string }
export interface TargetEnvironment { id: string; name: string }
export interface TargetServer { id: string; system_id: string; environment_id: string; hostname: string;
  ip_address: string; os: string; role: string; status: string }

type ServerTargetSelectorProps = {
  systems: TargetSystem[]
  environments: TargetEnvironment[]
  servers: TargetServer[]
  value: string
  onChange: (serverId: string) => void
  compact?: boolean
  layout?: 'split' | 'stacked' | 'sidebar'
}

export function ServerTargetSelector({ systems, environments, servers, value, onChange, compact = false, layout = 'split' }: ServerTargetSelectorProps) {
  const selected = servers.find((server) => server.id === value)
  const [systemId, setSystemId] = useState(selected?.system_id ?? '')
  const [environmentId, setEnvironmentId] = useState(selected?.environment_id ?? '')
  const effectiveSystemId = selected?.system_id ?? systemId
  const effectiveEnvironmentId = selected?.environment_id ?? environmentId
  const environmentIds = useMemo(() => new Set(servers
    .filter((server) => !effectiveSystemId || server.system_id === effectiveSystemId)
    .map((server) => server.environment_id)), [servers, effectiveSystemId])
  const availableEnvironments = environments.filter((environment) => environmentIds.has(environment.id))
  const availableServers = servers.filter((server) =>
    (!effectiveSystemId || server.system_id === effectiveSystemId) &&
    (!effectiveEnvironmentId || server.environment_id === effectiveEnvironmentId)
  )
  const visibleServerCount = effectiveSystemId && effectiveEnvironmentId ? availableServers.length : 0

  const stacked = layout === 'stacked'
  const sidebar = layout === 'sidebar'
  return <div className={cn('grid min-h-0 gap-4', !stacked && !sidebar && (compact ? 'lg:grid-cols-[minmax(190px,0.7fr)_minmax(280px,1.3fr)]' : 'md:grid-cols-[minmax(220px,0.75fr)_minmax(320px,1.25fr)]'))}>
    <div className={cn('grid gap-3', stacked ? 'sm:grid-cols-2' : 'grid-cols-1')}>
      <SelectControl label='System' value={effectiveSystemId} onChange={(next) => {
        setSystemId(next); setEnvironmentId(''); onChange('')
      }} options={systems.map((system) => ({ value: system.id, label: `${system.code} - ${system.name}`, keywords: system.name }))} />
      <SelectControl label='Environment' value={effectiveEnvironmentId} disabled={!effectiveSystemId} onChange={(next) => {
        setEnvironmentId(next); onChange('')
      }} options={availableEnvironments.map((environment) => ({ value: environment.id, label: environment.name }))} />
    </div>
    <div className='min-h-0 space-y-1'>
      <div className='flex items-center justify-between gap-2'>
        <Label className='text-xs text-muted-foreground'>Servers</Label>
        <span className='text-xs tabular-nums text-muted-foreground'>{visibleServerCount} available</span>
      </div>
      <div role='radiogroup' aria-label='Target server' className={cn('rounded-md border p-1.5', stacked ? 'grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3' : sidebar ? 'space-y-1' : 'max-h-56 space-y-1 overflow-y-auto')}>
        {!effectiveSystemId || !effectiveEnvironmentId ? <div className='grid min-h-28 place-items-center px-4 text-center text-sm text-muted-foreground'>
          Select a system and environment to list its servers.
        </div> : availableServers.length === 0 ? <div className='grid min-h-28 place-items-center px-4 text-center text-sm text-muted-foreground'>
          No servers match this target.
        </div> : availableServers.map((server) => {
          const active = server.id === value
          return <button key={server.id} type='button' role='radio' aria-checked={active} onClick={() => onChange(server.id)}
            className={cn('grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md border px-3 py-2 text-left transition-colors',
              active ? 'border-primary bg-primary/5' : 'border-transparent hover:border-border hover:bg-muted/60')}>
            <span className='min-w-0'>
              <span className='flex items-center gap-2 text-sm font-medium'><Server className='size-4 shrink-0' /><span className='break-all'>{server.hostname}</span></span>
              <span className='mt-1 flex items-center gap-2 text-xs text-muted-foreground'><Network className='size-3.5 shrink-0' />
                <span><span className='font-mono text-foreground'>{server.ip_address}</span> | {server.os} | {server.role}</span></span>
            </span>
            <span className='flex items-center gap-2'><StatusBadge value={server.status} />{active && <Check className='size-4 text-primary' />}</span>
          </button>
        })}
      </div>
      {selected && <p className='flex items-center gap-2 truncate pt-1 text-xs text-muted-foreground'><MonitorCog className='size-3.5 shrink-0' />
        Selected: <span className='font-medium text-foreground'>{selected.hostname}</span></p>}
    </div>
  </div>
}

function SelectControl({ label, value, options, disabled, onChange }: { label: string; value: string; options: Array<{ value: string; label: string; keywords?: string }>; disabled?: boolean; onChange: (value: string) => void }) {
  return <div className='min-w-0 space-y-1'><Label className='text-xs text-muted-foreground'>{label}</Label><SearchableSelect ariaLabel={`Target ${label.toLowerCase()}`} value={value} options={options} disabled={disabled}
    onValueChange={onChange} placeholder={`Select ${label.toLowerCase()}`} searchPlaceholder={`Search ${label.toLowerCase()}...`} /></div>
}
