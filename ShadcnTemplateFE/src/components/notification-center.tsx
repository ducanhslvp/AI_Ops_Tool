import { useQuery } from '@tanstack/react-query'
import { Bell, TriangleAlert } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { StatusBadge } from '@/features/aiops/status-badge'

interface NotificationData { metrics: { open_alerts: number }; alerts: Array<{ id: string; title: string; severity: string; created_at: string }> }

export function NotificationCenter() {
  const query = useQuery({ queryKey: ['dashboard'], queryFn: async () => (await apiClient.get<NotificationData>('/dashboard')).data, staleTime: 30_000 })
  const count = query.data?.metrics.open_alerts ?? 0
  return <Sheet><Tooltip><TooltipTrigger asChild><SheetTrigger asChild><Button variant='ghost' size='icon' className='relative rounded-full' aria-label='Notifications'>
    <Bell className='size-4' />{count > 0 && <span className='absolute right-0.5 top-0.5 min-w-3 rounded-full bg-destructive px-0.5 text-center text-[9px] leading-3 text-destructive-foreground'>{Math.min(count, 99)}</span>}
  </Button></SheetTrigger></TooltipTrigger><TooltipContent>Notifications</TooltipContent></Tooltip>
    <SheetContent className='overflow-y-auto sm:max-w-md'><SheetHeader><SheetTitle>Notifications</SheetTitle><SheetDescription>Current open infrastructure alerts from the platform database.</SheetDescription></SheetHeader>
      <div className='space-y-2 px-4 pb-6'>{(query.data?.alerts ?? []).map((alert) => <article key={alert.id} className='rounded-md border p-3'><div className='flex items-start gap-3'><TriangleAlert className='mt-0.5 size-4 shrink-0 text-muted-foreground' /><div className='min-w-0 flex-1'><p className='text-sm font-medium'>{alert.title}</p><p className='mt-1 text-xs text-muted-foreground'>{new Date(alert.created_at).toLocaleString()}</p></div><StatusBadge value={alert.severity} /></div></article>)}
        {!query.isLoading && !(query.data?.alerts.length) && <div className='py-16 text-center'><Bell className='mx-auto size-7 text-muted-foreground' /><p className='mt-3 font-medium'>No open alerts</p><p className='text-sm text-muted-foreground'>New platform alerts will appear here.</p></div>}</div>
    </SheetContent></Sheet>
}
