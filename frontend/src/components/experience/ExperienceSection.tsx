'use client'

import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
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

// Only projects are manually drag-reorderable. Work and education are
// auto-sorted by date (most recent first) and their order is derived, not stored.
const DRAGGABLE_KINDS = new Set<ExperienceKind>(['project'])
const DATE_SORTED_KINDS = new Set<ExperienceKind>(['work', 'education'])

const ONGOING_END_DATES = new Set(['', 'present', 'current', 'now', 'ongoing'])

function isOngoing(endDate?: string): boolean {
  return ONGOING_END_DATES.has((endDate ?? '').trim().toLowerCase())
}

// Sort key fallback to '' so missing dates compare consistently.
function dateValue(date?: string): string {
  return (date ?? '').trim()
}

/**
 * Compare two items so the most recent appears first:
 * 1. Ongoing roles (no end date / "Present") sort to the top.
 * 2. Then by end date descending.
 * 3. Then by start date descending as a tiebreaker.
 */
function compareByDateDesc(a: ExperienceItem, b: ExperienceItem): number {
  const aOngoing = isOngoing(a.end_date)
  const bOngoing = isOngoing(b.end_date)
  if (aOngoing !== bOngoing) return aOngoing ? -1 : 1

  const endCompare = dateValue(b.end_date).localeCompare(dateValue(a.end_date))
  if (endCompare !== 0) return endCompare

  return dateValue(b.start_date).localeCompare(dateValue(a.start_date))
}

interface SortableCardProps {
  item: ExperienceItem
  onEdit: () => void
  onDelete: () => void
}

function SortableCard({ item, onEdit, onDelete }: SortableCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
  })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    position: 'relative',
    zIndex: isDragging ? 1 : 'auto',
  }

  return (
    <div ref={setNodeRef} style={style}>
      <ExperienceCard
        item={item}
        onEdit={onEdit}
        onDelete={onDelete}
        draggable
        dragHandleProps={{ ...attributes, ...listeners }}
      />
    </div>
  )
}

interface ExperienceSectionProps {
  kind: ExperienceKind
  items: ExperienceItem[]
  onEdit: (item: ExperienceItem) => void
  onDelete: (item: ExperienceItem) => void
  onReorder?: (newItems: ExperienceItem[]) => void
}

export function ExperienceSection({ kind, items, onEdit, onDelete, onReorder }: ExperienceSectionProps) {
  const label = KIND_LABELS[kind]
  const isSkillSection = kind === 'skill'
  const isDraggableSection = DRAGGABLE_KINDS.has(kind)

  // Work/education order is derived from dates, so sort on every render —
  // editing a date naturally re-sorts the list next render.
  const displayItems = DATE_SORTED_KINDS.has(kind)
    ? [...items].sort(compareByDateDesc)
    : items

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = displayItems.findIndex(i => i.id === active.id)
    const newIndex = displayItems.findIndex(i => i.id === over.id)
    if (oldIndex === -1 || newIndex === -1) return
    onReorder?.(arrayMove(displayItems, oldIndex, newIndex))
  }

  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">{label}</h2>
        <span className="num text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
          {displayItems.length} item{displayItems.length !== 1 ? 's' : ''}
        </span>
      </div>
      {isSkillSection ? (
        <div className="p-4 flex flex-wrap gap-1.5">
          {displayItems.map(item => (
            <span key={item.id} className={`skill-tag ${getSkillVariant(item.content)}`}>
              {item.content}
            </span>
          ))}
        </div>
      ) : isDraggableSection ? (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={displayItems.map(i => i.id)} strategy={verticalListSortingStrategy}>
            <div className="divide-y divide-border">
              {displayItems.map(item => (
                <SortableCard
                  key={item.id}
                  item={item}
                  onEdit={() => onEdit(item)}
                  onDelete={() => onDelete(item)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <div className="divide-y divide-border">
          {displayItems.map(item => (
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
