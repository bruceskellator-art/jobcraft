'use client'

import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import { PlusIcon, UploadIcon } from 'lucide-react'
import type { ExperienceItem, ExperienceKind, CreateExperiencePayload } from '@/types/experience'
import {
  listExperience,
  createExperience,
  updateExperience,
  deleteExperience,
  importResume,
} from '@/lib/api'
import { ExperienceSection } from '@/components/experience/ExperienceSection'
import { ExperienceForm } from '@/components/experience/ExperienceForm'

const KIND_ORDER: ExperienceKind[] = ['work', 'project', 'education', 'skill', 'achievement']
const GRID_KINDS = new Set<ExperienceKind>(['skill', 'project'])

type ItemsByKind = Partial<Record<ExperienceKind, ExperienceItem[]>>

function groupByKind(items: ExperienceItem[]): ItemsByKind {
  return items.reduce<ItemsByKind>((acc, item) => {
    const list = acc[item.kind] ?? []
    return { ...acc, [item.kind]: [...list, item] }
  }, {})
}

export default function ExperiencePage() {
  const [items, setItems] = useState<ExperienceItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<ExperienceItem | undefined>(undefined)
  const [isSaving, setIsSaving] = useState(false)

  const [isImporting, setIsImporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function fetchItems() {
    setIsLoading(true)
    setLoadError(null)
    try {
      const data = await listExperience()
      setItems(data)
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load experience items.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchItems()
  }, [])

  function handleAddClick() {
    setEditingItem(undefined)
    setIsFormOpen(true)
  }

  function handleEditClick(item: ExperienceItem) {
    setEditingItem(item)
    setIsFormOpen(true)
  }

  async function handleDeleteClick(item: ExperienceItem) {
    const confirmed = window.confirm(`Delete this item?\n\n"${item.content.slice(0, 80)}"`)
    if (!confirmed) return
    try {
      await deleteExperience(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
      toast.success('Item deleted.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete item.')
    }
  }

  async function handleSave(payload: CreateExperiencePayload) {
    setIsSaving(true)
    try {
      if (editingItem) {
        const updated = await updateExperience(editingItem.id, payload)
        setItems(prev => prev.map(i => (i.id === updated.id ? updated : i)))
        toast.success('Item updated.')
      } else {
        const created = await createExperience(payload)
        setItems(prev => [...prev, created])
        toast.success('Item added.')
      }
      setIsFormOpen(false)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to save item.')
      throw err
    } finally {
      setIsSaving(false)
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setIsImporting(true)
    try {
      const result = await importResume(file)
      await fetchItems()
      toast.success(`Imported ${result.created.length} item${result.created.length !== 1 ? 's' : ''} from résumé.`)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setIsImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const grouped = groupByKind(items)
  const presentKinds = KIND_ORDER.filter(k => (grouped[k]?.length ?? 0) > 0)

  const fullWidthKinds = presentKinds.filter(k => !GRID_KINDS.has(k))
  const gridKinds = presentKinds.filter(k => GRID_KINDS.has(k))

  return (
    <>
      <Toaster />
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Experience corpus</h1>
          <p className="text-xs text-zinc-400">
            {isLoading ? 'Loading…' : `${items.length} item${items.length !== 1 ? 's' : ''} · the single source of truth every résumé claim is grounded in`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleImport}
          />
          <button
            className="btn btn-ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={isImporting}
          >
            <UploadIcon size={13} />
            {isImporting ? 'Importing…' : 'Import from PDF'}
          </button>
          <button className="btn btn-primary" onClick={handleAddClick}>
            <PlusIcon size={13} />
            Add item
          </button>
        </div>
      </header>

      <div className="p-6 space-y-5">
        {isLoading && (
          <div className="empty py-16">Loading experience items…</div>
        )}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
            <button
              onClick={() => void fetchItems()}
              className="ml-2 underline text-red-600 hover:text-red-800"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !loadError && items.length === 0 && (
          <div className="empty py-16">
            No experience items yet. Add your first item or import a résumé.
          </div>
        )}

        {!isLoading && !loadError && items.length > 0 && (
          <>
            {fullWidthKinds.map(kind => (
              <ExperienceSection
                key={kind}
                kind={kind}
                items={grouped[kind] ?? []}
                onEdit={handleEditClick}
                onDelete={handleDeleteClick}
              />
            ))}

            {gridKinds.length > 0 && (
              <div className={gridKinds.length > 1 ? 'grid grid-cols-2 gap-5' : ''}>
                {gridKinds.map(kind => (
                  <ExperienceSection
                    key={kind}
                    kind={kind}
                    items={grouped[kind] ?? []}
                    onEdit={handleEditClick}
                    onDelete={handleDeleteClick}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <ExperienceForm
        open={isFormOpen}
        onOpenChange={setIsFormOpen}
        initialData={editingItem}
        onSave={handleSave}
        isSaving={isSaving}
      />
    </>
  )
}
