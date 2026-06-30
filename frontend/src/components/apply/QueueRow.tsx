import type { ApplyQueueItem, ApplicationStatus } from '@/types/apply'
import { scoreColor } from '@/lib/scoreColor'
import { getSkillVariant } from '@/components/experience/skillTagHelper'
import { Checkbox } from '@/components/ui/checkbox'
import { CompanyLogo } from '@/components/common/CompanyLogo'
import { sourceLabel } from '@/lib/sources'

const MAX_SKILLS = 3

const DOT_COLORS: Record<ApplicationStatus, string> = {
  queued:    '#a1a1aa',
  filling:   '#3b82f6',
  review:    '#f59e0b',
  submitted: '#10b981',
  failed:    '#f43f5e',
  blocked:   '#f43f5e',
}

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  queued:    'Queued',
  filling:   'Filling',
  review:    'Review',
  submitted: 'Submitted',
  failed:    'Failed',
  blocked:   'Blocked',
}

interface QueueRowProps {
  item: ApplyQueueItem
  isSelected: boolean
  isChecked: boolean
  onSelect: () => void
  onCheck: (checked: boolean) => void
}

export function QueueRow({ item, isSelected, isChecked, onSelect, onCheck }: QueueRowProps) {
  const { application, field_map, job } = item
  const status = application.status
  const confidence = field_map?.overall_confidence ?? application.apply_confidence

  // Derive skill tags from job title words as a best-effort
  const titleSkills = job.title
    .split(/[\s,/&]+/)
    .filter(w => w.length > 2)
    .slice(0, MAX_SKILLS)

  return (
    <tr
      className="data-row cursor-pointer"
      style={isSelected ? { borderLeft: '3px solid #4f46e5', background: '#f5f3ff' } : {}}
      onClick={onSelect}
    >
      <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
        <Checkbox
          checked={isChecked}
          onCheckedChange={onCheck}
        />
      </td>

      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <CompanyLogo company={job.company} size="sm" />
          <div>
            <p className="text-sm font-semibold text-foreground leading-tight">{job.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{job.company}</p>
            <div className="flex flex-wrap gap-1 mt-1">
              <span className="source-pill">{sourceLabel(job.source)}</span>
              {titleSkills.map(skill => (
                <span key={skill} className={`skill-tag ${getSkillVariant(skill)}`}>
                  {skill}
                </span>
              ))}
            </div>
          </div>
        </div>
      </td>

      <td className="px-3 py-3 text-xs text-muted-foreground num">—</td>

      <td className="px-3 py-3">
        <span className={`chip ${scoreColor(confidence)}`}>
          {Math.round(confidence * 100)}%
        </span>
      </td>

      <td className="px-3 py-3">
        <span className={`badge badge-${status}`}>
          <span className="dot" style={{ background: DOT_COLORS[status] }} />
          {STATUS_LABELS[status]}
        </span>
      </td>
    </tr>
  )
}
