import { Outlet } from '@tanstack/react-router'
import { Server, Bot, TerminalSquare } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { SidebarNav } from './components/sidebar-nav'

const sidebarNavItems = [
  {
    title: 'AI Providers',
    href: '/settings',
    icon: <Bot size={18} />,
  },
  {
    title: 'SSH Gateways',
    href: '/settings/account',
    icon: <Server size={18} />,
  },
  {
    title: 'SSH Commands',
    href: '/settings/ssh-commands',
    icon: <TerminalSquare size={18} />,
  },
]

export function Settings() {
  return (
    <>
      {/* ===== Top Heading ===== */}
      <Header>
        <Search className='me-auto' />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main fixed>
        <div className='space-y-0.5'>
          <h1 className='text-2xl font-bold tracking-tight md:text-3xl'>
            Settings
          </h1>
          <p className='text-muted-foreground'>
            Manage the active AI runtime and backend-controlled SSH Gateway.
          </p>
        </div>
        <Separator className='my-4 lg:my-6' />
        <div className='flex min-w-0 flex-1 flex-col gap-4 overflow-hidden lg:flex-row lg:gap-6'>
          <aside className='top-0 shrink-0 lg:sticky lg:w-56'>
            <SidebarNav items={sidebarNavItems} />
          </aside>
          <div className='flex min-w-0 flex-1 overflow-y-hidden p-1'>
            <Outlet />
          </div>
        </div>
      </Main>
    </>
  )
}
