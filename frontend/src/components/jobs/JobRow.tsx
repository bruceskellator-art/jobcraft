import Link from 'next/link'
import type { JobPosting } from '@/types/job'
import { getSkillVariant } from '@/components/experience/skillTagHelper'
import { relativeTime } from '@/lib/relativeTime'

const MAX_SKILLS = 4

function getLogoColors(company: string): { bg: string; color: string } {
  const PALETTES = [
    { bg: '#ede9fe', color: '#5b21b6' },
    { bg: '#fce7f3', color: '#be185d' },
    { bg: '#e0e7ff', color: '#4338ca' },
    { bg: '#d1fae5', color: '#065f46' },
    { bg: '#ffedd5', color: '#c2410c' },
    { bg: '#fef9c3', color: '#92400e' },
    { bg: '#e0f2fe', color: '#075985' },
    { bg: '#fce7f3', color: '#9d174d' },
  ]
  let hash = 0
  for (let i = 0; i < company.length; i++) {
    hash = (hash * 31 + company.charCodeAt(i)) >>> 0
  }
  return PALETTES[hash % PALETTES.length]
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
}

function sourceLabel(source: string): string {
  const MAP: Record<string, string> = {
    greenhouse: 'GH',
    lever: 'LV',
    linkedin: 'LI',
    mcf: 'MCF',
  }
  return MAP[source.toLowerCase()] ?? source.slice(0, 3).toUpperCase()
}

function fitChipClass(score: number): string {
  if (score >= 0.75) return 'chip-high'
  if (score >= 0.5) return 'chip-mid'
  return 'chip-low'
}

interface JobRowProps {
  job: JobPosting
}

export function JobRow({ job }: JobRowProps) {
  const displayTitle = job.extracted?.title ?? job.title
  const displayCompany = job.extracted?.company ?? job.company
  const displayLocation = job.extracted?.location ?? job.location
  const remotePolicy = job.extracted?.remote_policy ?? job.remote_policy
  const skills = job.extracted?.required_skills ?? []
  const visibleSkills = skills.slice(0, MAX_SKILLS)

  const logoColors = getLogoColors(displayCompany)
  const initials = getInitials(displayCompany)
  const age = relativeTime(job.scraped_at)

  const locationText = [displayLocation, remotePolicy].filter(Boolean).join(' · ')

  return (
    <tr className="data-row">
      {/* Fit chip */}
      <td className="px-4 py-3">
        {job.match ? (
          <span
            className={`chip ${fitChipClass(job.match.overall_score)}`}
            title={`Overall fit: ${Math.round(job.match.overall_score * 100)}%`}
          >
            {Math.round(job.match.overall_score * 100)}%
          </span>
        ) : (
          <span
            className="chip"
            style={{ background: '#f4f4f5', color: '#71717a', borderColor: '#e4e4e7' }}
            title="Fit score not yet computed"
          >
            —
          </span>
        )}
      </td>

      {/* Role + Skills */}
      <td className="px-4 py-3">
        <a
          href={job.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-zinc-900 hover:underline text-sm"
          style={{ textDecorationColor: '#6366f1' }}
        >
          {displayTitle}
        </a>
        {visibleSkills.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {visibleSkills.map(skill => (
              <span key={skill} className={`skill-tag ${getSkillVariant(skill)}`}>
                {skill}
              </span>
            ))}
            {skills.length > MAX_SKILLS && (
              <span className="skill-tag skill-gen">+{skills.length - MAX_SKILLS}</span>
            )}
          </div>
        )}
      </td>

      {/* Company */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <div
            className="logo-avatar"
            style={{
              background: logoColors.bg,
              color: logoColors.color,
              width: '1.75rem',
              height: '1.75rem',
              fontSize: '0.55rem',
            }}
          >
            {initials}
          </div>
          <span className="text-sm font-medium text-zinc-700">{displayCompany}</span>
        </div>
      </td>

      {/* Location */}
      <td className="px-4 py-3 text-xs text-zinc-500">
        {locationText || <span className="text-zinc-300">—</span>}
      </td>

      {/* Age */}
      <td className="px-4 py-3 text-xs text-zinc-400 num">{age}</td>

      {/* Action */}
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1.5">
          <span className="source-pill">{sourceLabel(job.source)}</span>
          <Link href={`/jobs/${job.id}`} className="btn btn-ghost text-xs">
            View →
          </Link>
        </div>
      </td>
    </tr>
  )
}
