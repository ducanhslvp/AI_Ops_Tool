import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const PAGE_SIZES = [10, 20, 50, 100, 200]

export function DataTablePagination({ page, pageSize, total, visibleRows, onPageChange,
  onPageSizeChange }: { page: number; pageSize: number; total: number; visibleRows: number;
  onPageChange: (page: number) => void; onPageSizeChange: (size: number) => void }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  return <div className='flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm'>
    <span className='text-muted-foreground'>{visibleRows} visible - {total} total rows</span>
    <div className='flex flex-wrap items-center gap-2'>
      <label className='flex items-center gap-2 whitespace-nowrap text-muted-foreground'>Rows per page
        <select aria-label='Rows per page' value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}
          className='h-8 rounded-md border bg-background px-2 text-foreground'>
          {PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
      <Button title='First page' size='icon' variant='outline' disabled={page === 0} onClick={() => onPageChange(0)}>
        <ChevronsLeft className='size-4' /></Button>
      <Button size='sm' variant='outline' disabled={page === 0} onClick={() => onPageChange(page - 1)}>Previous</Button>
      <label className='flex items-center gap-2 whitespace-nowrap text-muted-foreground'>Page
        <Input aria-label='Go to page' type='number' min={1} max={pageCount} value={page + 1}
          onChange={(event) => onPageChange(Math.min(pageCount - 1, Math.max(0, Number(event.target.value) - 1)))}
          className='h-8 w-16' />of {pageCount}</label>
      <Button size='sm' variant='outline' disabled={page >= pageCount - 1} onClick={() => onPageChange(page + 1)}>Next</Button>
      <Button title='Last page' size='icon' variant='outline' disabled={page >= pageCount - 1}
        onClick={() => onPageChange(pageCount - 1)}><ChevronsRight className='size-4' /></Button>
    </div>
  </div>
}
