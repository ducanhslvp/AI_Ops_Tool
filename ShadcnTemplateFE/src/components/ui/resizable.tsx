import { GripVertical } from 'lucide-react'
import * as ResizablePrimitive from 'react-resizable-panels'
import { cn } from '@/lib/utils'

function ResizablePanelGroup({
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Group>) {
  return (
    <ResizablePrimitive.Group
      data-slot='resizable-panel-group'
      className={cn(
        'flex h-full w-full data-[orientation=vertical]:flex-col',
        className
      )}
      {...props}
    />
  )
}

const ResizablePanel = ResizablePrimitive.Panel

function ResizableHandle({
  withHandle,
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Separator> & {
  withHandle?: boolean
}) {
  return (
    <ResizablePrimitive.Separator
      data-slot='resizable-handle'
      className={cn(
        'group relative flex w-px shrink-0 items-center justify-center bg-border outline-none transition-colors hover:bg-primary/60 focus-visible:bg-primary focus-visible:ring-1 focus-visible:ring-ring aria-[orientation=horizontal]:h-px aria-[orientation=horizontal]:w-full',
        className
      )}
      {...props}
    >
      {withHandle && (
        <span className='z-10 flex h-8 w-3 items-center justify-center rounded-sm border bg-background shadow-xs group-aria-[orientation=horizontal]:h-3 group-aria-[orientation=horizontal]:w-8'>
          <GripVertical className='size-3 group-aria-[orientation=horizontal]:rotate-90' />
        </span>
      )}
    </ResizablePrimitive.Separator>
  )
}

export { ResizableHandle, ResizablePanel, ResizablePanelGroup }
