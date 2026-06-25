'use client'

import type { JobPosting } from '@/types/job'
import { ApplicationCard } from './ApplicationCard'
import type { ApplicationCardData } from './ApplicationCard'

interface KanbanColumnProps {
  id: string
  label: string
  dotColor: string
  countColor: string
  countBg: string
  applications: ApplicationCardData[]
  jobsById: Map<string, JobPosting>
  onStatusChange: (id: string, status: string) => void
  onDrop: (columnId: string, applicationId: string) => void
}

export function KanbanColumn({
  id,
  label,
  dotColor,
  countColor,
  countBg,
  applications,
  jobsById,
  onStatusChange,
  onDrop,
}: KanbanColumnProps) {
  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    const applicationId = e.dataTransfer.getData('application_id')
    if (applicationId) {
      onDrop(id, applicationId)
    }
  }

  return (
    <div onDragOver={handleDragOver} onDrop={handleDrop}>
      <div className="card-col-header">
        <div className="flex items-center gap-1.5">
          <span className="col-dot" style={{ background: dotColor }} />
          <span className="text-xs font-semibold text-muted-foreground">{label}</span>
        </div>
        <span
          className="num text-xs px-1.5 py-0.5 rounded-full"
          style={{ color: countColor, background: countBg }}
        >
          {applications.length}
        </span>
      </div>

      {applications.length === 0 ? (
        <div className="border border-dashed border-border rounded-xl p-8">
          <div className="empty">No {label.toLowerCase()}</div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {applications.map((app) => (
            <ApplicationCard
              key={app.id}
              application={app}
              job={jobsById.get(app.job_id)}
              onStatusChange={onStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  )
}
