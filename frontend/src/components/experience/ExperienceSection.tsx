'use client'

import type { ExperienceItem, ExperienceKind } from '@/types/experience'
import { ExperienceCard } from './ExperienceCard'
import { getSkillVariant } from './skillTagHelper'

const KIND_LABELS: Record<ExperienceKind, string> = {
  work: 'Work',
  project: 'Projects',
  education: 'Education',
  skill: 'Skills',
  achievement: 'Achievements',
}

interface ExperienceSectionProps {
  kind: ExperienceKind
  items: ExperienceItem[]
  onEdit: (item: ExperienceItem) => void
  onDelete: (item: ExperienceItem) => void
}

export function ExperienceSection({ kind, items, onEdit, onDelete }: ExperienceSectionProps) {
  const label = KIND_LABELS[kind]
  const isSkillSection = kind === 'skill'

  return (
    <section className="bg-white border border-zinc-200 rounded-xl">
      <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{label}</h2>
        <span className="num text-xs text-zinc-400 bg-zinc-100 px-2 py-0.5 rounded-full">
          {items.length} item{items.length !== 1 ? 's' : ''}
        </span>
      </div>
      {isSkillSection ? (
        <div className="p-4 flex flex-wrap gap-1.5">
          {items.map(item => (
            <span
              key={item.id}
              className={`skill-tag ${getSkillVariant(item.content)}`}
            >
              {item.content}
            </span>
          ))}
        </div>
      ) : (
        <div className="divide-y divide-zinc-100">
          {items.map(item => (
            <ExperienceCard
              key={item.id}
              item={item}
              onEdit={() => onEdit(item)}
              onDelete={() => onDelete(item)}
            />
          ))}
        </div>
      )}
    </section>
  )
}
