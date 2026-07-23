import { Badge } from '@/components/ui/badge'

const statusVariant: Record<
  string,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  online: 'default',
  allow: 'default',
  success: 'default',
  ready: 'default',
  degraded: 'secondary',
  warning: 'secondary',
  pending: 'secondary',
  maintenance: 'outline',
  approval_required: 'outline',
  offline: 'destructive',
  critical: 'destructive',
  deny: 'destructive',
  blocked: 'destructive',
}

export function StatusBadge({ value }: { value: string | null | undefined }) {
  const normalized = value?.trim() || 'unknown'
  return (
    <Badge variant={statusVariant[normalized.toLowerCase()] ?? 'outline'}>
      {normalized.replace(/_/g, ' ')}
    </Badge>
  )
}
