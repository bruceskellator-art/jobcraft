'use client'

import type { JobPosting } from '@/types/job'
import { scoreColor } from '@/lib/scoreColor'
import { relativeTime } from '@/lib/relativeTime'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export interface ApplicationCardData {
  id: string
  job_id: string
  status: string
  submitted_at: string | null
}

interface ApplicationCardProps {
  application: ApplicationCardData
  job: JobPosting | undefined
  onStatusChange: (id: string, status: string) => void
}

const STATUS_OPTIONS = [
  { value: 'submitted', label: 'Submitted' },
  { value: 'phone_screen', label: 'Phone Screen' },
  { value: 'technical', label: 'Technical' },
  { value: 'onsite', label: 'Onsite' },
  { value: 'offer', label: 'Offer' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'withdrawn', label: 'Withdrawn' },
]

const AVATAR_PALETTES: Array<{ bg: string; color: string }> = [
  { bg: '#ede9fe', color: '#5b21b6' },
  { bg: '#e0f2fe', color: '#0369a1' },
  { bg: '#fce7f3', color: '#be185d' },
  { bg: '#d1fae5', color: '#065f46' },
  { bg: '#fff7ed', color: '#c2410c' },
  { bg: '#e0e7ff', color: '#4338ca' },
  { bg: '#f0fdf4', color: '#15803d' },
  { bg: '#f1f5f9', color: '#334155' },
]

function getAvatarColors(letter: string): { bg: string; color: string } {
  const idx = letter.charCodeAt(0) % AVATAR_PALETTES.length
  return AVATAR_PALETTES[idx] ?? AVATAR_PALETTES[0]!
}

function getInitials(company: string): string {
  const words = company.trim().split(/\s+/)
  if (words.length >= 2) {
    return ((words[0]?.[0] ?? '') + (words[1]?.[0] ?? '')).toUpperCase()
  }
  return company.slice(0, 2).toUpperCase()
}

function getCardClass(status: string): string {
  if (status === 'offer') return 'card-offer'
  if (status === 'rejected' || status === 'withdrawn') return 'card-muted'
  if (['phone_screen', 'technical', 'onsite'].includes(status)) return 'card-active'
  return ''
}

export function ApplicationCard({ application, job, onStatusChange }: ApplicationCardProps) {
  const company = job?.company ?? 'Unknown'
  const title = job?.title ?? 'Unknown Role'
  const source = job?.source ?? ''
  const skills = job?.extracted?.required_skills?.slice(0, 3) ?? []
  const matchScore = job?.match?.overall_score ?? null
  const initials = getInitials(company)
  const avatarColors = getAvatarColors(initials[0] ?? 'A')
  const cardClass = getCardClass(application.status)
  const timeAgo = application.submitted_at ? relativeTime(application.submitted_at) : null

  function handleDragStart(e: React.DragEvent<HTMLDivElement>) {
    e.dataTransfer.setData('application_id', application.id)
  }

  function handleStatusValueChange(value: string | null) {
    if (value === null) return
    onStatusChange(application.id, value)
  }

  return (
    <div
      className={`kanban-card ${cardClass}`}
      draggable
      onDragStart={handleDragStart}
    >
      <div className="flex items-center gap-2">
        <div
          className="logo-avatar"
          style={{ background: avatarColors.bg, color: avatarColors.color }}
        >
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-zinc-700 truncate">{company}</span>
            {source && <span className="source-pill">{source.slice(0, 3).toUpperCase()}</span>}
          </div>
          {timeAgo && (
            <div className="text-[0.68rem] text-zinc-400">Singapore · {timeAgo}</div>
          )}
        </div>
        {matchScore !== null && (
          <span className={`chip ${scoreColor(matchScore)} self-start`}>
            {matchScore.toFixed(2)}
          </span>
        )}
      </div>

      <div className="text-sm font-medium text-zinc-800 leading-snug">{title}</div>

      {skills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {skills.map((skill) => (
            <span key={skill} className="skill-tag skill-gen">
              {skill}
            </span>
          ))}
        </div>
      )}

      <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
        <Select value={application.status} onValueChange={handleStatusValueChange}>
          <SelectTrigger size="sm" className="w-full text-xs text-zinc-500">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
