'use client'

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import type { ExperienceItem, ExperienceKind, CreateExperiencePayload } from '@/types/experience'

const KIND_OPTIONS: ExperienceKind[] = ['work', 'project', 'education', 'skill', 'achievement']

interface ExperienceFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialData?: ExperienceItem
  onSave: (payload: CreateExperiencePayload) => Promise<void>
  isSaving: boolean
}

function buildInitialState(item?: ExperienceItem): CreateExperiencePayload {
  return {
    kind: item?.kind ?? 'work',
    title: item?.title ?? '',
    organization: item?.organization ?? '',
    start_date: item?.start_date ?? '',
    end_date: item?.end_date ?? '',
    content: item?.content ?? '',
    tags: item?.tags ?? [],
  }
}

export function ExperienceForm({ open, onOpenChange, initialData, onSave, isSaving }: ExperienceFormProps) {
  const [form, setForm] = useState<CreateExperiencePayload>(() => buildInitialState(initialData))
  const [tagsInput, setTagsInput] = useState(initialData?.tags.join(', ') ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Resetting derived form state when the dialog reopens is intentional —
    // this is a controlled reset, not a cascading render loop.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm(buildInitialState(initialData))
    setTagsInput(initialData?.tags.join(', ') ?? '')
    setError(null)
  }, [initialData, open])

  function handleField(field: keyof CreateExperiencePayload, value: string) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.content.trim()) {
      setError('Content is required.')
      return
    }
    setError(null)
    const tags = tagsInput
      .split(',')
      .map(t => t.trim())
      .filter(Boolean)
    try {
      await onSave({ ...form, tags })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save.')
    }
  }

  const inputClass = 'w-full border border-zinc-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600/40'
  const labelClass = 'block text-xs font-medium text-zinc-600 mb-1'

  function handleOpenChange(next: boolean) {
    if (!next && isSaving) return
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{initialData ? 'Edit experience item' : 'Add experience item'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3 mt-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="kind" className={labelClass}>Kind</label>
              <select
                id="kind"
                name="kind"
                value={form.kind}
                onChange={e => handleField('kind', e.target.value)}
                className={inputClass}
              >
                {KIND_OPTIONS.map(k => (
                  <option key={k} value={k}>{k.charAt(0).toUpperCase() + k.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="title" className={labelClass}>Title</label>
              <input
                id="title"
                name="title"
                type="text"
                value={form.title ?? ''}
                onChange={e => handleField('title', e.target.value)}
                placeholder="e.g. Software Engineer"
                className={inputClass}
              />
            </div>
          </div>
          <div>
            <label htmlFor="organization" className={labelClass}>Organization</label>
            <input
              id="organization"
              name="organization"
              type="text"
              value={form.organization ?? ''}
              onChange={e => handleField('organization', e.target.value)}
              placeholder="e.g. Traveloka"
              className={inputClass}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="start_date" className={labelClass}>Start date</label>
              <input
                id="start_date"
                name="start_date"
                type="text"
                value={form.start_date ?? ''}
                onChange={e => handleField('start_date', e.target.value)}
                placeholder="e.g. 2022"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="end_date" className={labelClass}>End date</label>
              <input
                id="end_date"
                name="end_date"
                type="text"
                value={form.end_date ?? ''}
                onChange={e => handleField('end_date', e.target.value)}
                placeholder="e.g. present"
                className={inputClass}
              />
            </div>
          </div>
          <div>
            <label htmlFor="content" className={labelClass}>Content <span className="text-red-500">*</span></label>
            <textarea
              id="content"
              name="content"
              value={form.content}
              onChange={e => handleField('content', e.target.value)}
              placeholder="Describe the achievement, skill, or experience…"
              rows={3}
              className={inputClass}
              required
            />
          </div>
          <div>
            <label htmlFor="tags" className={labelClass}>Tags (comma-separated)</label>
            <input
              id="tags"
              name="tags"
              type="text"
              value={tagsInput}
              onChange={e => setTagsInput(e.target.value)}
              placeholder="e.g. Python, FastAPI, PostgreSQL"
              className={inputClass}
            />
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <DialogFooter>
            <button type="submit" disabled={isSaving} className="btn btn-primary">
              {isSaving ? 'Saving…' : 'Save'}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
