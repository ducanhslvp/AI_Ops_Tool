import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function QueryLoadError({ visible, message, onRetry, retrying = false }: { visible: boolean; message: string;
  onRetry: () => void | Promise<unknown>; retrying?: boolean }) {
  if (!visible) return null
  return <div role='alert' className='mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3'>
    <p className='flex items-center gap-2 text-sm'><AlertCircle className='size-4 text-destructive' />{message}</p>
    <Button type='button' size='sm' variant='outline' disabled={retrying} onClick={() => void onRetry()}><RefreshCw className={retrying ? 'size-4 animate-spin' : 'size-4'} />Retry</Button>
  </div>
}
