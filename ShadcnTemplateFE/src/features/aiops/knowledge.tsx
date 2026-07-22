import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, ChevronRight, Download, Eye, FileText, FileUp, RefreshCw, SearchCode, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'

interface KnowledgeRecord { id: string; system_id: string; title: string; document_type: string;
  source_uri: string; content_text: string; graph_nodes: unknown[]; graph_edges: unknown[]; updated_at: string }
interface SystemRecord { id: string; code: string; name: string }

export function KnowledgePage() {
  const client = useQueryClient(); const inputRef = useRef<HTMLInputElement>(null); const [query, setQuery] = useState('')
  const [systemId, setSystemId] = useState(''); const [systemQuery, setSystemQuery] = useState(''); const [sort, setSort] = useState('updated')
  const [preview, setPreview] = useState<KnowledgeRecord>(); const [deleting, setDeleting] = useState<KnowledgeRecord>()
  const documentsQuery = useQuery({ queryKey: ['knowledge'], queryFn: async () =>
    (await apiClient.get<KnowledgeRecord[]>('/knowledge', { params: { page: 1, page_size: 200 } })).data })
  const systemsQuery = useQuery({ queryKey: ['inventory', 'systems'], queryFn: async () =>
    (await apiClient.get<SystemRecord[]>('/inventory/systems', { params: { page: 1, page_size: 200 } })).data })
  const activeSystemId = systemId || systemsQuery.data?.[0]?.id || ''
  const visibleSystems = useMemo(() => (systemsQuery.data ?? []).filter((system) =>
    `${system.code} ${system.name}`.toLowerCase().includes(systemQuery.trim().toLowerCase())), [systemQuery, systemsQuery.data])
  const documents = useMemo(() => [...(documentsQuery.data ?? [])]
    .filter((item) => item.system_id === activeSystemId && JSON.stringify(item).toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title) : new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
  [activeSystemId, documentsQuery.data, query, sort])
  const groups = useMemo(() => groupDocuments(documents), [documents])
  const exportList = () => { const csv = ['title,type,system_id,updated_at', ...documents.map((item) =>
    [item.title, item.document_type, item.system_id, item.updated_at].map((value) => `"${String(value).replace(/"/g, '""')}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); const link = document.createElement('a')
    link.href = url; link.download = 'knowledge-index.csv'; link.click(); URL.revokeObjectURL(url) }
  const upload = useMutation({ mutationFn: async (file: File) => { if (!activeSystemId) throw new Error('system')
    const form = new FormData(); form.append('system_id', activeSystemId); form.append('title', file.name.replace(/\.[^.]+$/, '')); form.append('file', file)
    return apiClient.post('/knowledge/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } }) },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['knowledge'] }); toast.success('Document uploaded and indexed.') },
    onError: () => toast.error('Select a System and a valid PDF, DOCX, Markdown or TXT file.') })
  const reindex = useMutation({ mutationFn: async (id: string) => apiClient.post(`/knowledge/${id}/reindex`),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['knowledge'] }); toast.success('Knowledge index refreshed.') },
    onError: () => toast.error('Document could not be re-indexed.') })
  const remove = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/knowledge/${id}`), onSuccess: async () => {
    setDeleting(undefined); await client.invalidateQueries({ queryKey: ['knowledge'] }); toast.success('Document deleted.') }, onError: () => toast.error('Delete failed.') })
  const download = async (item: KnowledgeRecord) => { try { const response = await apiClient.get(`/knowledge/${item.id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = url; link.download = item.title; link.click(); URL.revokeObjectURL(url)
  } catch { toast.error('Download failed.') } }
  return <><Header><Search /><ThemeSwitch /><ProfileDropdown /></Header><Main><div className='mb-4 flex flex-wrap items-center justify-between gap-3'>
    <div><h1 className='text-2xl font-semibold tracking-tight'>Knowledge Base</h1><p className='text-sm text-muted-foreground'>System-owned evidence used by AI, discovery, and dependency analysis.</p></div>
    <div className='flex gap-2'><input ref={inputRef} type='file' className='hidden' accept='.pdf,.docx,.md,.txt' onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); event.target.value = '' }} />
      <Button size='sm' variant='outline' onClick={exportList}><Download className='size-4' />Export</Button>
      <Button size='sm' disabled={upload.isPending || !activeSystemId} onClick={() => inputRef.current?.click()}><FileUp className='size-4' />Upload to System</Button></div></div>
    <div className='grid min-h-[600px] overflow-hidden rounded-md border lg:grid-cols-[280px_1fr]'><aside className='border-b bg-muted/15 p-3 lg:border-b-0 lg:border-r'><p className='mb-2 px-2 text-xs font-medium uppercase text-muted-foreground'>Systems</p>
      <div className='relative mb-3'><SearchCode className='absolute start-2.5 top-2.5 size-4 text-muted-foreground' /><Input className='ps-8' value={systemQuery} onChange={(event) => setSystemQuery(event.target.value)} placeholder='Search systems' aria-label='Search systems' /></div>
      <nav className='max-h-72 space-y-1 overflow-y-auto pe-1'>{visibleSystems.map((system) => { const count = (documentsQuery.data ?? []).filter((item) => item.system_id === system.id).length; const active = activeSystemId === system.id
        return <button key={system.id} type='button' onClick={() => setSystemId(system.id)} className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm ${active ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'}`}>
          <BookOpen className='size-4' /><span className='min-w-0 flex-1'><span className='block truncate font-medium'>{system.code}</span><span className='block truncate text-xs text-muted-foreground'>{system.name}</span></span><span className='text-xs text-muted-foreground'>{count}</span><ChevronRight className='size-3.5' /></button> })}</nav>
      {!visibleSystems.length && <p className='px-2 py-6 text-center text-sm text-muted-foreground'>No matching Systems.</p>}
      {activeSystemId && <div className='mt-5 border-t pt-3'><p className='mb-2 px-2 text-xs font-medium uppercase text-muted-foreground'>Document tree</p>{groups.map(([category, items]) => <div key={category} className='flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground'><FileText className='size-3.5' /><span className='flex-1'>{category}</span><span>{items.length}</span></div>)}</div>}</aside>
      <section className='min-w-0 p-4'><div className='mb-4 flex flex-wrap gap-2'><div className='relative min-w-56 flex-1'><SearchCode className='absolute start-2 top-2.5 size-4 text-muted-foreground' /><Input className='ps-8' value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search this System knowledge' /></div>
        <select aria-label='Knowledge sort' value={sort} onChange={(event) => setSort(event.target.value)} className='h-9 rounded-md border bg-background px-3 text-sm'><option value='updated'>Recently updated</option><option value='title'>Title</option></select></div>
        <div className='max-h-[650px] space-y-6 overflow-y-auto pe-1'>{groups.map(([category, items]) => <section key={category}><div className='mb-2 flex items-center justify-between'><h2 className='font-medium'>{category}</h2><span className='text-xs text-muted-foreground'>{items.length} documents</span></div>
          <div className='grid gap-2 xl:grid-cols-2'>{items.map((item) => <article key={item.id} className='rounded-md border p-3'><div className='flex items-start justify-between gap-2'><div className='min-w-0'><h3 className='truncate text-sm font-medium'>{item.title}</h3><p className='mt-1 text-xs text-muted-foreground'>{item.document_type} / {new Date(item.updated_at).toLocaleString()}</p></div><span className='text-xs text-muted-foreground'>{item.graph_nodes.length} nodes</span></div>
            <p className='mt-3 line-clamp-2 text-sm text-muted-foreground'>{item.content_text || 'No extracted text'}</p><div className='mt-3 flex gap-1'><Button title='Preview' size='icon' variant='ghost' onClick={() => setPreview(item)}><Eye className='size-4' /></Button><Button title='Download' size='icon' variant='ghost' onClick={() => download(item)}><Download className='size-4' /></Button><Button title='Re-index' size='icon' variant='ghost' onClick={() => reindex.mutate(item.id)}><RefreshCw className='size-4' /></Button><Button title='Delete' size='icon' variant='ghost' onClick={() => setDeleting(item)}><Trash2 className='size-4' /></Button></div></article>)}</div></section>)}
          {!documents.length && <div className='grid min-h-72 place-items-center text-center'><div><BookOpen className='mx-auto size-8 text-muted-foreground' /><p className='mt-3 font-medium'>No knowledge for this System</p><p className='text-sm text-muted-foreground'>Upload a README, architecture, network, runbook, or deployment document.</p></div></div>}</div></section></div>
    <Dialog open={Boolean(preview)} onOpenChange={(open) => !open && setPreview(undefined)}><DialogContent className='max-h-[85svh] max-w-3xl overflow-auto'><DialogHeader><DialogTitle>{preview?.title}</DialogTitle><DialogDescription>Extracted content used by the knowledge index.</DialogDescription></DialogHeader><pre className='whitespace-pre-wrap text-sm'>{preview?.content_text}</pre></DialogContent></Dialog>
    <ConfirmDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)} title='Delete knowledge document?' desc='The stored source and indexed content will be removed.' destructive isLoading={remove.isPending} handleConfirm={() => deleting && remove.mutate(deleting.id)} />
  </Main></>
}

function groupDocuments(documents: KnowledgeRecord[]): Array<[string, KnowledgeRecord[]]> { const groups = new Map<string, KnowledgeRecord[]>(); for (const item of documents) { const category = knowledgeCategory(item); groups.set(category, [...(groups.get(category) ?? []), item]) } return [...groups.entries()] }
function knowledgeCategory(item: KnowledgeRecord) { const value = `${item.title} ${item.document_type}`.toLowerCase(); if (value.includes('readme')) return 'README'; if (value.includes('architect')) return 'Architecture'
  if (value.includes('network')) return 'Network'; if (value.includes('runbook')) return 'Runbook'; if (value.includes('deploy')) return 'Deployment'; if (value.includes('diagram')) return 'Diagram'; return 'Documents' }
