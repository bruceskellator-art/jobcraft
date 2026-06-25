import Link from 'next/link'
import type { JobPosting } from '@/types/job'
import { getSkillVariant } from '@/components/experience/skillTagHelper'
import { relativeTime } from '@/lib/relativeTime'
import { CompanyLogo } from '@/components/common/CompanyLogo'

const MAX_SKILLS = 4

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
          className="font-semibold text-foreground hover:underline text-sm"
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
          <CompanyLogo company={displayCompany} size="sm" />
          <span className="text-sm font-medium text-foreground">{displayCompany}</span>
        </div>
      </td>

      {/* Location */}
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {locationText || <span className="text-muted-foreground">—</span>}
      </td>

      {/* Age */}
      <td className="px-4 py-3 text-xs text-muted-foreground num">{age}</td>

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
