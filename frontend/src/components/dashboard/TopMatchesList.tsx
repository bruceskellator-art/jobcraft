import Link from 'next/link'
import { CompanyLogo } from '@/components/common/CompanyLogo'

type SkillVariant = 'skill-ml' | 'skill-fe' | 'skill-be' | 'skill-infra' | 'skill-gen'
type ChipVariant = 'chip-high' | 'chip-mid' | 'chip-low'

interface SkillTag {
  label: string
  variant: SkillVariant
}

interface JobMatch {
  id: string
  company: string
  title: string
  skills: SkillTag[]
  source: string
  age: string
  score: string
  chipVariant: ChipVariant
}

const TOP_MATCHES: JobMatch[] = [
  {
    id: 'fde',
    company: 'Stripe',
    title: 'Forward Deployed Engineer',
    skills: [
      { label: 'Python', variant: 'skill-be' },
      { label: 'React', variant: 'skill-fe' },
      { label: 'SQL', variant: 'skill-gen' },
    ],
    source: 'GH',
    age: '1d',
    score: '0.89',
    chipVariant: 'chip-high',
  },
  {
    id: 'aise',
    company: 'Brainbase',
    title: 'AI Solutions Engineer',
    skills: [
      { label: 'Python', variant: 'skill-ml' },
      { label: 'LLMs', variant: 'skill-ml' },
      { label: 'PyTorch', variant: 'skill-ml' },
    ],
    source: 'LI',
    age: '2d',
    score: '0.81',
    chipVariant: 'chip-high',
  },
  {
    id: 'aie',
    company: 'Greythorn',
    title: 'AI Engineer (LLM Platform)',
    skills: [
      { label: 'Python', variant: 'skill-ml' },
      { label: 'FastAPI', variant: 'skill-be' },
      { label: 'RAG', variant: 'skill-ml' },
    ],
    source: 'MCF',
    age: '3d',
    score: '0.64',
    chipVariant: 'chip-mid',
  },
]

export function TopMatchesList() {
  return (
    <section className="col-span-2 bg-white border border-zinc-200 rounded-xl">
      <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Top new matches today</h2>
        <Link
          href="/jobs"
          className="text-xs font-medium"
          style={{ color: '#4f46e5' }}
        >
          See all 34 →
        </Link>
      </div>
      <div className="divide-y divide-zinc-100">
        {TOP_MATCHES.map((job) => (
          <div
            key={job.id}
            className="flex items-center gap-3 px-4 py-3 data-row"
          >
            <CompanyLogo company={job.company} size="sm" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-zinc-800">{job.title}</div>
              <div className="flex items-center gap-1.5 mt-1">
                {job.skills.map((skill) => (
                  <span key={skill.label} className={`skill-tag ${skill.variant}`}>
                    {skill.label}
                  </span>
                ))}
                <span className="source-pill ml-0.5">{job.source}</span>
              </div>
            </div>
            <div className="text-xs text-zinc-400 w-12 text-right num flex-none">
              {job.age}
            </div>
            <span className={`chip ${job.chipVariant} flex-none`}>{job.score}</span>
            <Link href="/jobs" className="btn btn-ghost text-xs flex-none">
              View
            </Link>
          </div>
        ))}
      </div>
    </section>
  )
}
