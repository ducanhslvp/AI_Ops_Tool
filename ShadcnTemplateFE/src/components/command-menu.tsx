import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  ArrowRight,
  Bot,
  ChevronRight,
  FileText,
  Laptop,
  LoaderCircle,
  Moon,
  Plug,
  Server,
  ShieldCheck,
  Sun,
  User,
} from 'lucide-react'
import { useSearch } from '@/context/search-provider'
import { useTheme } from '@/context/theme-provider'
import { apiClient } from '@/lib/api-client'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { sidebarData } from './layout/data/sidebar-data'
import { ScrollArea } from './ui/scroll-area'

interface SearchResult {
  kind: string
  id: string
  title: string
  subtitle: string
  url: string
}

const resultIcons: Record<string, React.ElementType> = {
  server: Server,
  system: Server,
  knowledge: FileText,
  report: FileText,
  policy: ShieldCheck,
  plugin: Plug,
  ai_session: Bot,
  user: User,
}

export function CommandMenu() {
  const navigate = useNavigate()
  const { setTheme } = useTheme()
  const { open, setOpen } = useSearch()
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [query])

  const searchQuery = useQuery({
    queryKey: ['global-search', debouncedQuery],
    queryFn: async () =>
      (await apiClient.get<{ items: SearchResult[] }>('/search', {
        params: { q: debouncedQuery, limit: 5 },
      })).data.items,
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 30_000,
  })

  const runCommand = React.useCallback(
    (command: () => unknown) => {
      setOpen(false)
      command()
    },
    [setOpen]
  )

  return (
    <CommandDialog modal open={open} onOpenChange={(nextOpen) => {
      setOpen(nextOpen)
      if (!nextOpen) setQuery('')
    }}>
      <CommandInput
        value={query}
        onValueChange={setQuery}
        placeholder='Search systems, servers, knowledge, reports...'
      />
      <CommandList>
        <ScrollArea type='hover' className='h-72 pe-1'>
          <CommandEmpty>No results found.</CommandEmpty>
          {searchQuery.isFetching && (
            <div className='flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground'>
              <LoaderCircle className='size-4 animate-spin' /> Searching platform data
            </div>
          )}
          {!!searchQuery.data?.length && (
            <CommandGroup heading='Platform results'>
              {searchQuery.data.map((item) => {
                const Icon = resultIcons[item.kind] ?? ArrowRight
                return (
                  <CommandItem
                    key={`${item.kind}-${item.id}`}
                    value={`${item.title} ${item.subtitle} ${item.kind}`}
                    onSelect={() => runCommand(() => navigate({ to: item.url }))}
                  >
                    <Icon className='size-4' />
                    <div className='min-w-0 flex-1'>
                      <p className='truncate'>{item.title}</p>
                      <p className='truncate text-xs text-muted-foreground'>
                        {item.kind.replace('_', ' ')} · {item.subtitle}
                      </p>
                    </div>
                    <ChevronRight className='size-4' />
                  </CommandItem>
                )
              })}
            </CommandGroup>
          )}
          {!!searchQuery.data?.length && <CommandSeparator />}
          {sidebarData.navGroups.map((group) => (
            <CommandGroup key={group.title} heading={group.title}>
              {group.items.map((navItem, i) => {
                if (navItem.url)
                  return (
                    <CommandItem
                      key={`${navItem.url}-${i}`}
                      value={navItem.title}
                      onSelect={() => {
                        runCommand(() => navigate({ to: navItem.url }))
                      }}
                    >
                      <div className='flex size-4 items-center justify-center'>
                        <ArrowRight className='size-2 text-muted-foreground/80' />
                      </div>
                      {navItem.title}
                    </CommandItem>
                  )

                return navItem.items?.map((subItem, i) => (
                  <CommandItem
                    key={`${navItem.title}-${subItem.url}-${i}`}
                    value={`${navItem.title}-${subItem.url}`}
                    onSelect={() => {
                      runCommand(() => navigate({ to: subItem.url }))
                    }}
                  >
                    <div className='flex size-4 items-center justify-center'>
                      <ArrowRight className='size-2 text-muted-foreground/80' />
                    </div>
                    {navItem.title} <ChevronRight /> {subItem.title}
                  </CommandItem>
                ))
              })}
            </CommandGroup>
          ))}
          <CommandSeparator />
          <CommandGroup heading='Theme'>
            <CommandItem onSelect={() => runCommand(() => setTheme('light'))}>
              <Sun /> <span>Light</span>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => setTheme('dark'))}>
              <Moon className='scale-90' />
              <span>Dark</span>
            </CommandItem>
            <CommandItem onSelect={() => runCommand(() => setTheme('system'))}>
              <Laptop />
              <span>System</span>
            </CommandItem>
          </CommandGroup>
        </ScrollArea>
      </CommandList>
    </CommandDialog>
  )
}
