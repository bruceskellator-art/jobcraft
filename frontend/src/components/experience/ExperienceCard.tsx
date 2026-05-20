'use client'

import { PencilIcon, Trash2Icon } from 'lucide-react'
import type { ExperienceItem } from '@/types/experience'
import { getSkillVariant } from './skillTagHelper'

interface ExperienceCardProps {
  item: ExperienceItem
  onEdit: () => void
  onDelete: () => void
}

function getLogoInitials(organization?: string): string {
  if (!organization) return '?'
  return organization
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0])
    .join('')
    .toUpperCase()
}

function buildSubtitle(item: ExperienceItem): string {
  const parts: string[] = []
  if (item.title) parts.push(item.title)
  if (item.organization) parts.push(item.organization)
  const dateRange = [item.start_date, item.end_date].filter(Boolean).join('–')
  if (dateRange) parts.push(dateRange)
  return parts.join(' · ')
}

export function ExperienceCard({ item, onEdit, onDelete }: ExperienceCardProps) {
  const subtitle = buildSubtitle(item)
  const shortId = `exp_${item.id.slice(0, 4)}`

  return (
    <div className="data-row group px-4 py-3.5 flex items-start gap-3">
      <span className="num text-xs text-zinc-400 w-16 flex-none pt-0.5 mt-0.5">{shortId}</span>
      {item.organization && (
        <div
          className="logo-avatar flex-none mt-0.5"
          style={{ background: '#e0f2fe', color: '#0369a1', width: '2rem', height: '2rem', fontSize: '0.55rem' }}
        >
          {getLogoInitials(item.organization)}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-zinc-800">{item.content}</div>
        {subtitle && <div className="text-xs text-zinc-500 mt-0.5">{subtitle}</div>}
        {item.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {item.tags.map(tag => (
              <span key={tag} className={`skill-tag ${getSkillVariant(tag)}`}>{tag}</span>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-none">
        <button
          onClick={onEdit}
          className="p-1 rounded hover:bg-zinc-100 text-zinc-400 hover:text-zinc-700 transition-colors"
          aria-label="Edit item"
        >
          <PencilIcon size={13} />
        </button>
        <button
          onClick={onDelete}
          className="p-1 rounded hover:bg-red-50 text-zinc-400 hover:text-red-600 transition-colors"
          aria-label="Delete item"
        >
          <Trash2Icon size={13} />
        </button>
      </div>
    </div>
  )
}
