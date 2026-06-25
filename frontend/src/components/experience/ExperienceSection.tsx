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

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = items.findIndex(i => i.id === active.id)
    const newIndex = items.findIndex(i => i.id === over.id)
    if (oldIndex === -1 || newIndex === -1) return
    onReorder?.(arrayMove(items, oldIndex, newIndex))
  }

  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">{label}</h2>
        <span className="num text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
          {items.length} item{items.length !== 1 ? 's' : ''}
        </span>
      </div>
      {isSkillSection ? (
        <div className="p-4 flex flex-wrap gap-1.5">
          {items.map(item => (
            <span key={item.id} className={`skill-tag ${getSkillVariant(item.content)}`}>
              {item.content}
            </span>
          ))}
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={items.map(i => i.id)} strategy={verticalListSortingStrategy}>
            <div className="divide-y divide-border">
              {items.map(item => (
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
      )}
    </section>
  )
}
