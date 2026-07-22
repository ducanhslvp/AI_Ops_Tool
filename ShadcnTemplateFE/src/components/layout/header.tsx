import { Children, isValidElement } from 'react'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { ContextualHelp } from '@/components/contextual-help'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { ConfigDrawer } from '@/components/config-drawer'

type HeaderProps = React.HTMLAttributes<HTMLElement> & {
  fixed?: boolean
  ref?: React.Ref<HTMLElement>
}

export function Header({ className, fixed, children, ...props }: HeaderProps) {
  void fixed
  const extras = Children.toArray(children).filter((child) =>
    !isValidElement(child) || ![Search, ThemeSwitch, ConfigDrawer, ProfileDropdown].includes(child.type as never)
  )
  return (
    <header
      className={cn(
        'header-fixed peer/header sticky top-0 z-50 h-16 w-full shrink-0 border-b bg-background/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/80',
        className
      )}
      {...props}
    >
      <div
        className={cn(
          'relative flex h-full items-center gap-3 p-4 sm:gap-4'
        )}
      >
        <SidebarTrigger variant='outline' className='max-md:scale-125' />
        <Separator orientation='vertical' className='h-6' />
        <div className='min-w-0 flex-1'>{extras}</div>
        <div className='ms-auto flex shrink-0 items-center justify-end gap-1'>
          <Search className='hidden md:flex' />
          <ContextualHelp />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </div>
    </header>
  )
}
