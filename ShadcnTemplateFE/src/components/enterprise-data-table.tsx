import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Columns3, MoreHorizontal, Search, Trash2, type LucideIcon } from 'lucide-react'
import {
  type ColumnDef, type ColumnSizingState, type PaginationState, type Row, type SortingState, type VisibilityState,
  flexRender, getCoreRowModel, getFilteredRowModel, getPaginationRowModel,
  getSortedRowModel, useReactTable,
} from '@tanstack/react-table'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { DataTablePagination } from '@/components/data-table'
import { DataTableBulkActions } from '@/components/data-table/bulk-actions'
import { DEFAULT_ROWS_PER_PAGE } from '@/lib/pagination'

export type EnterpriseColumn<T> = {
  id: string
  header: string
  accessor: (record: T) => unknown
  cell?: (record: T) => React.ReactNode
  size?: number
  minSize?: number
  enableHiding?: boolean
  className?: string
  wrap?: boolean
}

type EnterpriseRowAction<T> = {
  label: string
  icon?: LucideIcon
  destructive?: boolean
  disabled?: (record: T) => boolean
  hidden?: (record: T) => boolean
  onSelect: (record: T) => void
}

type EnterpriseBulkAction<T> = {
  label: string
  icon?: LucideIcon
  destructive?: boolean
  onSelect: (records: T[]) => void | Promise<void>
}

type EnterpriseDataTableProps<T> = {
  data: T[]
  columns: EnterpriseColumn<T>[]
  getRowId: (record: T) => string
  loading?: boolean
  searchPlaceholder?: string
  filterSlot?: React.ReactNode
  rowActions?: EnterpriseRowAction<T>[]
  bulkActions?: EnterpriseBulkAction<T>[]
  emptyTitle?: string
  emptyDescription?: string
  initialPageSize?: number
  entityName?: string
  className?: string
  rowPreview?: (record: T) => React.ReactNode
  rowPreviewDelayMs?: number
}

export function EnterpriseDataTable<T>({ data, columns, getRowId, loading = false,
  searchPlaceholder = 'Search loaded data', filterSlot, rowActions = [], bulkActions = [],
  emptyTitle = 'No matching records', emptyDescription = 'Adjust search or filters to view records.',
  initialPageSize = DEFAULT_ROWS_PER_PAGE, entityName = 'row', className, rowPreview,
  rowPreviewDelayMs = 0 }: EnterpriseDataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [visibility, setVisibility] = useState<VisibilityState>({})
  const [sizing, setSizing] = useState<ColumnSizingState>({})
  const [selection, setSelection] = useState({})
  const [globalFilter, setGlobalFilter] = useState('')
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: initialPageSize })
  const [context, setContext] = useState<{ row: Row<T>; x: number; y: number }>()
  const [preview, setPreview] = useState<{ record: T; x: number; y: number }>()
  const previewTimerRef = useRef<number | undefined>(undefined)
  useEffect(() => () => {
    if (previewTimerRef.current) window.clearTimeout(previewTimerRef.current)
  }, [])
  const definitions = useMemo<ColumnDef<T>[]>(() => [
    {
      id: 'select', size: 42, minSize: 42, maxSize: 42, enableSorting: false, enableHiding: false,
      header: ({ table }) => <Checkbox aria-label='Select all visible rows' checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && 'indeterminate')}
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(Boolean(value))} />,
      cell: ({ row }) => <Checkbox aria-label='Select row' checked={row.getIsSelected()} onCheckedChange={(value) => row.toggleSelected(Boolean(value))} />,
    },
    ...columns.map((column): ColumnDef<T> => ({
      id: column.id, accessorFn: column.accessor, size: column.size ?? 180, minSize: column.minSize ?? 100,
      enableHiding: column.enableHiding !== false,
      header: ({ column: tableColumn }) => <button type='button' className='flex w-full items-center gap-1 text-left font-medium'
        onClick={tableColumn.getToggleSortingHandler()}>{column.header}<SortIcon direction={tableColumn.getIsSorted()} /></button>,
      cell: ({ row }) => column.cell ? column.cell(row.original) : String(column.accessor(row.original) ?? ''),
      meta: { className: column.className, wrap: column.wrap },
    })),
    ...(rowActions.length ? [{
      id: 'actions', size: 56, minSize: 56, maxSize: 56, enableSorting: false, enableHiding: false,
      header: () => <span className='sr-only'>Actions</span>,
      cell: ({ row }: { row: Row<T> }) => <RowActions record={row.original} actions={rowActions} />,
    } as ColumnDef<T>] : []),
  ], [columns, rowActions])
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data, columns: definitions, getRowId, enableRowSelection: true, enableColumnResizing: true,
    columnResizeMode: 'onChange', state: { sorting, columnVisibility: visibility, columnSizing: sizing,
      rowSelection: selection, globalFilter, pagination },
    onSortingChange: setSorting, onColumnVisibilityChange: setVisibility, onColumnSizingChange: setSizing,
    onRowSelectionChange: setSelection, onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    globalFilterFn: (row, _column, value) => JSON.stringify(row.original).toLowerCase().includes(String(value).toLowerCase()),
    getCoreRowModel: getCoreRowModel(), getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(), getPaginationRowModel: getPaginationRowModel(),
  })
  const selected = table.getSelectedRowModel().rows.map((row) => row.original)
  return <div className={cn('min-w-0 space-y-3', className)}>
    <div className='flex flex-wrap items-center gap-2'><div className='relative min-w-56 flex-1'><Search className='absolute left-2.5 top-2.5 size-4 text-muted-foreground' />
      <Input value={globalFilter} onChange={(event) => setGlobalFilter(event.target.value)} className='pl-8' placeholder={searchPlaceholder} /></div>{filterSlot}
      <DropdownMenu><DropdownMenuTrigger asChild><Button variant='outline' size='sm'><Columns3 className='size-4' />Columns</Button></DropdownMenuTrigger>
        <DropdownMenuContent align='end'><DropdownMenuLabel>Visible columns</DropdownMenuLabel><DropdownMenuSeparator />
          {table.getAllLeafColumns().filter((column) => column.getCanHide()).map((column) => <DropdownMenuCheckboxItem key={column.id} checked={column.getIsVisible()}
            onCheckedChange={(value) => column.toggleVisibility(Boolean(value))}>{columns.find((item) => item.id === column.id)?.header ?? column.id}</DropdownMenuCheckboxItem>)}</DropdownMenuContent></DropdownMenu>
    </div>
    <div className='relative max-h-[min(62svh,640px)] min-h-44 w-full overflow-auto rounded-md border'>
      <table className='w-full table-fixed border-separate border-spacing-0 text-sm' style={{ minWidth: table.getCenterTotalSize() }}><thead className='sticky top-0 z-20 bg-background shadow-[0_1px_0_hsl(var(--border))]'>
        {table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id} style={{ width: header.getSize() }}
          className={cn('relative h-10 border-b bg-background px-3 text-left align-middle font-medium whitespace-nowrap', header.column.id === 'actions' && 'sticky right-0 z-30 shadow-[-1px_0_0_hsl(var(--border))]')}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
          {header.column.getCanResize() && <button aria-label={`Resize ${header.id} column`} onDoubleClick={() => header.column.resetSize()} onMouseDown={header.getResizeHandler()} onTouchStart={header.getResizeHandler()}
            className={cn('absolute right-0 top-0 h-full w-1 cursor-col-resize touch-none select-none hover:bg-primary/40', header.column.getIsResizing() && 'bg-primary')} />}</th>)}</tr>)}</thead>
        <tbody>{loading ? <LoadingRows columns={table.getVisibleLeafColumns().length} /> : table.getRowModel().rows.length ? table.getRowModel().rows.map((row) => <tr key={row.id}
          data-state={row.getIsSelected() ? 'selected' : undefined} onContextMenu={(event) => { if (!rowActions.length) return; event.preventDefault(); setContext({ row, x: event.clientX, y: event.clientY }) }}
          onMouseEnter={(event) => {
            if (!rowPreview) return
            if (previewTimerRef.current) window.clearTimeout(previewTimerRef.current)
            const rect = event.currentTarget.getBoundingClientRect()
            const next = { record: row.original, x: Math.min(rect.left + 48, window.innerWidth - 440), y: Math.min(rect.bottom + 6, window.innerHeight - 260) }
            previewTimerRef.current = window.setTimeout(() => setPreview(next), rowPreviewDelayMs)
          }}
          onMouseLeave={() => {
            if (previewTimerRef.current) window.clearTimeout(previewTimerRef.current)
            setPreview(undefined)
          }}
          className='group/row border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted'>{row.getVisibleCells().map((cell) => { const meta = cell.column.columnDef.meta as { className?: string; wrap?: boolean } | undefined
            const value = cell.getValue(); const title = typeof value === 'string' || typeof value === 'number' ? String(value) : undefined
            return <td key={cell.id} style={{ width: cell.column.getSize() }} title={title}
              className={cn('overflow-hidden border-b p-3 align-middle', meta?.wrap ? 'break-words whitespace-normal' : 'text-ellipsis whitespace-nowrap', cell.column.id === 'actions' && 'sticky right-0 z-10 bg-background shadow-[-1px_0_0_hsl(var(--border))] group-hover/row:bg-muted', meta?.className)}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>})}</tr>) :
          <tr><td colSpan={table.getVisibleLeafColumns().length} className='h-44 text-center'><div className='mx-auto max-w-sm space-y-1'><p className='font-medium'>{emptyTitle}</p><p className='text-sm text-muted-foreground'>{emptyDescription}</p></div></td></tr>}</tbody></table>
    </div>
    <DataTablePagination table={table} />
    <DataTableBulkActions table={table} entityName={entityName}>{bulkActions.map((action) => { const Icon = action.icon ?? (action.destructive ? Trash2 : undefined); return <Button key={action.label} size='sm' variant={action.destructive ? 'destructive' : 'outline'}
      onClick={() => void action.onSelect(selected)}>{Icon && <Icon className='size-4' />}{action.label}</Button> })}</DataTableBulkActions>
    <ContextActions context={context} actions={rowActions} onClose={() => setContext(undefined)} />
    {preview && rowPreview && <div role='status' aria-label='Row preview' className='pointer-events-none fixed z-50 w-[min(26rem,calc(100vw-2rem))] rounded-md border bg-popover p-3 text-popover-foreground shadow-lg' style={{ left: Math.max(16, preview.x), top: Math.max(16, preview.y) }}>{rowPreview(preview.record)}</div>}
  </div>
}

function SortIcon({ direction }: { direction: false | 'asc' | 'desc' }) {
  const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown
  return <Icon className='size-3.5 text-muted-foreground' />
}

function RowActions<T>({ record, actions }: { record: T; actions: EnterpriseRowAction<T>[] }) {
  const visible = actions.filter((action) => !action.hidden?.(record))
  return <DropdownMenu><DropdownMenuTrigger asChild><Button aria-label='Open row actions' size='icon' variant='ghost'><MoreHorizontal className='size-4' /></Button></DropdownMenuTrigger>
    <DropdownMenuContent align='end'>{visible.map((action) => { const Icon = action.icon; return <DropdownMenuItem key={action.label} disabled={action.disabled?.(record)}
      className={action.destructive ? 'text-destructive focus:text-destructive' : undefined} onSelect={() => action.onSelect(record)}>{Icon && <Icon className='size-4' />}{action.label}</DropdownMenuItem> })}</DropdownMenuContent></DropdownMenu>
}

function ContextActions<T>({ context, actions, onClose }: { context?: { row: Row<T>; x: number; y: number }; actions: EnterpriseRowAction<T>[]; onClose: () => void }) {
  return <DropdownMenu open={Boolean(context)} onOpenChange={(open) => !open && onClose()}><DropdownMenuTrigger asChild><button type='button' aria-hidden tabIndex={-1}
    className='pointer-events-none fixed size-px opacity-0' style={{ left: context?.x ?? 0, top: context?.y ?? 0 }} /></DropdownMenuTrigger>
    <DropdownMenuContent>{context && actions.filter((action) => !action.hidden?.(context.row.original)).map((action) => { const Icon = action.icon; return <DropdownMenuItem key={action.label}
      disabled={action.disabled?.(context.row.original)} className={action.destructive ? 'text-destructive focus:text-destructive' : undefined}
      onSelect={() => action.onSelect(context.row.original)}>{Icon && <Icon className='size-4' />}{action.label}</DropdownMenuItem> })}</DropdownMenuContent></DropdownMenu>
}

function LoadingRows({ columns }: { columns: number }) {
  return <>{Array.from({ length: 6 }, (_, row) => <tr key={row}>{Array.from({ length: columns }, (_unused, column) => <td key={column} className='border-b p-3'><Skeleton className='h-5 w-full' /></td>)}</tr>)}</>
}
