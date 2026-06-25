import { CompanyLogo } from '@/components/common/CompanyLogo'

type SkillVariant = 'skill-ml' | 'skill-fe' | 'skill-be' | 'skill-infra' | 'skill-gen'
type ChipVariant = 'chip-high' | 'chip-mid' | 'chip-low'
type BadgeVariant =
  | 'badge-submitted'
  | 'badge-review'
  | 'badge-filling'
  | 'badge-blocked'
  | 'badge-queued'
  | 'badge-failed'

interface SkillTag {
  label: string
  variant: SkillVariant
}

interface ActivityRow {
  id: string
  time: string
  company: string
  description: string
  jobTitle: string
  note?: string
  noteColor?: string
  skills: SkillTag[]
  score: string
  chipVariant: ChipVariant
  badgeVariant: BadgeVariant
  badgeDotColor: string
  badgeLabel: string
}

const ACTIVITY_ROWS: ActivityRow[] = [
  {
    id: 'act-1',
    time: '09:41',
    company: 'Stripe',
    description: 'Auto-submitted',
    jobTitle: 'Forward Deployed Engineer',
    skills: [
      { label: 'Python', variant: 'skill-be' },
      { label: 'React', variant: 'skill-fe' },
    ],
    score: '0.89',
    chipVariant: 'chip-high',
    badgeVariant: 'badge-submitted',
    badgeDotColor: 'bg-emerald-500',
    badgeLabel: 'auto',
  },
  {
    id: 'act-2',
    time: '09:38',
    company: 'Greythorn',
    description: 'Queued for review',
    jobTitle: 'AI Engineer (LLM Platform)',
    note: '(unknown screening Q)',
    noteColor: 'text-amber-600',
    skills: [
      { label: 'Python', variant: 'skill-ml' },
      { label: 'RAG', variant: 'skill-ml' },
    ],
    score: '0.62',
    chipVariant: 'chip-mid',
    badgeVariant: 'badge-review',
    badgeDotColor: 'bg-amber-500',
    badgeLabel: 'review',
  },
  {
    id: 'act-3',
    time: '09:30',
    company: 'Brainbase',
    description: 'Generated resume + cover letter',
    jobTitle: 'AI Solutions Engineer',
    skills: [
      { label: 'LLMs', variant: 'skill-ml' },
      { label: 'PyTorch', variant: 'skill-ml' },
    ],
    score: '0.79',
    chipVariant: 'chip-high',
    badgeVariant: 'badge-filling',
    badgeDotColor: 'bg-blue-500',
    badgeLabel: 'filling',
  },
  {
    id: 'act-4',
    time: '09:12',
    company: 'Shopee',
    description: 'Blocked',
    jobTitle: 'Senior Backend Engineer',
    note: '· Workday CAPTCHA',
    skills: [
      { label: 'Go', variant: 'skill-be' },
      { label: 'Redis', variant: 'skill-infra' },
    ],
    score: '0.41',
    chipVariant: 'chip-low',
    badgeVariant: 'badge-blocked',
    badgeDotColor: 'bg-rose-500',
    badgeLabel: 'blocked',
  },
]

export function RecentActivity() {
  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold">Recent activity</h2>
      </div>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-border">
          {ACTIVITY_ROWS.map((row) => (
            <tr key={row.id} className="data-row">
              <td className="px-4 py-2.5 w-16 text-xs text-muted-foreground num">
                {row.time}
              </td>
              <td className="px-4 py-2.5 w-10">
                <CompanyLogo company={row.company} size="sm" />
              </td>
              <td className="px-2 py-2.5">
                <span className="text-foreground">
                  {row.description} ·{' '}
                  <span className="font-semibold text-foreground">
                    {row.jobTitle}
                  </span>
                  {row.note && (
                    <span className={`text-xs ${row.noteColor ?? 'text-muted-foreground'}`}>
                      {' '}{row.note}
                    </span>
                  )}
                </span>
                <div className="flex gap-1 mt-1">
                  {row.skills.map((skill) => (
                    <span key={skill.label} className={`skill-tag ${skill.variant}`}>
                      {skill.label}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-2.5 text-right">
                <span className={`chip ${row.chipVariant}`}>{row.score}</span>
              </td>
              <td className="px-4 py-2.5 text-right">
                <span className={`badge ${row.badgeVariant}`}>
                  <span className={`dot ${row.badgeDotColor}`} />
                  {row.badgeLabel}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
