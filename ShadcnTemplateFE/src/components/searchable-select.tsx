import { useState } from 'react'
import { Check, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

type SearchableSelectOption = {
  value: string
  label: string
  keywords?: string
  disabled?: boolean
}

type SearchableSelectProps = {
  value: string
  options: SearchableSelectOption[]
  onValueChange: (value: string) => void
  placeholder?: string
  searchPlaceholder?: string
  emptyMessage?: string
  ariaLabel: string
  disabled?: boolean
  className?: string
  allowClear?: boolean
}

export function SearchableSelect({ value, options, onValueChange, placeholder = 'Select an option',
  searchPlaceholder = 'Search...', emptyMessage = 'No results found.', ariaLabel, disabled = false,
  className, allowClear = false }: SearchableSelectProps) {
  const [open, setOpen] = useState(false)
  const selected = options.find((option) => option.value === value)
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild><Button type='button' role='combobox' aria-label={ariaLabel} aria-expanded={open} disabled={disabled}
      variant='outline' className={cn('h-9 w-full min-w-0 justify-between px-3 font-normal', !selected && 'text-muted-foreground', className)}>
      <span className='min-w-0 truncate' title={selected?.label}>{selected?.label ?? placeholder}</span><ChevronsUpDown className='size-4 shrink-0 opacity-50' />
    </Button></PopoverTrigger>
    <PopoverContent className='w-[var(--radix-popover-trigger-width)] min-w-64 p-0' align='start'>
      <Command><CommandInput placeholder={searchPlaceholder} /><CommandList><CommandEmpty>{emptyMessage}</CommandEmpty><CommandGroup>
        {allowClear && <CommandItem value={`${placeholder} clear`} onSelect={() => { onValueChange(''); setOpen(false) }}><Check className={cn('size-4', value ? 'opacity-0' : 'opacity-100')} />{placeholder}</CommandItem>}
        {options.map((option) => <CommandItem key={option.value} value={`${option.label} ${option.keywords ?? ''}`} disabled={option.disabled}
          onSelect={() => { onValueChange(option.value); setOpen(false) }}><Check className={cn('size-4 shrink-0', value === option.value ? 'opacity-100' : 'opacity-0')} />
          <span className='min-w-0 whitespace-normal break-words' title={option.label}>{option.label}</span></CommandItem>)}
      </CommandGroup></CommandList></Command>
    </PopoverContent>
  </Popover>
}
