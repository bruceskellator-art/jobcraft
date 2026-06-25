'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { Toaster } from '@/components/ui/sonner'
import type { JobPosting } from '@/types/job'
import type { MatchRead } from '@/types/match'
import { getJob, getJobMatch } from '@/lib/api'
import { MatchBreakdown } from '@/components/jobs/MatchBreakdown'
import { GenerationPanel } from '@/components/jobs/GenerationPanel'
import { getSkillVariant } from '@/components/experience/skillTagHelper'
import { CompanyLogo } from '@/components/common/CompanyLogo'

type PageState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; job: JobPosting; match: MatchRead | null }

function sourceLabel(source: string): string {
  const MAP: Record<string, string> = {
    greenhouse: 'GH',
    lever: 'LV',
    linkedin: 'LI',
    mcf: 'MCF',
  }
  return MAP[source.toLowerCase()] ?? source.slice(0, 3).toUpperCase()
}

function formatSalary(min?: number, max?: number): string | null {
  if (!min && !max) return null
  const fmt = (n: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
  if (min && max) return `${fmt(min)} – ${fmt(max)}`
  if (min) return `From ${fmt(min)}`
  if (max) return `Up to ${fmt(max)}`
  return null
}

export default function JobDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id

  const [state, setState] = useState<PageState>({ status: 'loading' })

  useEffect(() => {
    if (!id) return
    const controller = new AbortController()

    async function load() {
      setState({ status: 'loading' })
      try {
        const job = await getJob(id, controller.signal)
        if (controller.signal.aborted) return

        // If the job already carries a match score, use it directly
        if (job.match) {
          setState({ status: 'success', job, match: job.match })
          return
        }

        // Otherwise fetch the match endpoint (computes on-demand)
        try {
          const match = await getJobMatch(id, controller.signal)
          if (!controller.signal.aborted) {
            setState({ status: 'success', job, match })
          }
        } catch {
          // Match scoring is optional — still show the job without it
          if (!controller.signal.aborted) {
            setState({ status: 'success', job, match: null })
          }
        }
      } catch (err: unknown) {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            message: err instanceof Error ? err.message : 'Failed to load job.',
          })
        }
      }
    }

    void load()
    return () => controller.abort()
  }, [id])

  if (state.status === 'loading') {
    return (
      <>
        <Toaster />
        <header className="h-14 bg-white border-b border-zinc-200 flex items-center px-6 sticky top-0 z-10">
          <Link href="/jobs" className="text-zinc-400 hover:text-zinc-700 text-sm">
            ← Jobs
          </Link>
        </header>
        <div className="p-6">
          <div className="empty py-16">Loading job…</div>
        </div>
      </>
    )
  }

  if (state.status === 'error') {
    return (
      <>
        <Toaster />
        <header className="h-14 bg-white border-b border-zinc-200 flex items-center px-6 sticky top-0 z-10">
          <Link href="/jobs" className="text-zinc-400 hover:text-zinc-700 text-sm">
            ← Jobs
          </Link>
        </header>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {state.message}
          </div>
        </div>
      </>
    )
  }

  const { job, match } = state
  const displayTitle = job.extracted?.title ?? job.title
  const displayCompany = job.extracted?.company ?? job.company
  const displayLocation = job.extracted?.location ?? job.location
  const remotePolicy = job.extracted?.remote_policy ?? job.remote_policy
  const seniority = job.extracted?.seniority
  const salaryText = formatSalary(job.extracted?.salary_min_usd, job.extracted?.salary_max_usd)
  const locationText = [displayLocation, remotePolicy].filter(Boolean).join(' · ')

  return (
    <>
      <Toaster />

      {/* Header */}
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <Link href="/jobs" className="text-zinc-400 hover:text-zinc-700 text-sm">
            ← Jobs
          </Link>
          <div className="flex items-center gap-2.5">
            <CompanyLogo company={displayCompany} size="md" />
            <div>
              <h1 className="text-sm font-semibold">{displayTitle}</h1>
              <p className="text-xs text-zinc-400">
                {displayCompany}
                {locationText ? ` · ${locationText}` : ''}
                {seniority ? ` · ${seniority}` : ''}
                {' · '}
                <span className="source-pill">{sourceLabel(job.source)}</span>
              </p>
            </div>
          </div>
        </div>
        <a
          href={job.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-ghost text-xs"
        >
          View original →
        </a>
      </header>

      {/* Body */}
      <div className="p-6 space-y-5 max-w-3xl">

        {/* Match breakdown */}
        {match ? (
          <MatchBreakdown match={match} />
        ) : (
          <section className="bg-white border border-zinc-200 rounded-xl px-4 py-6 text-sm text-zinc-400 text-center">
            No match score yet — click <strong className="text-zinc-600">Run matches</strong> on the jobs list to compute it.
          </section>
        )}

        {/* Extracted from listing */}
        {job.extracted && (
          <section className="bg-white border border-zinc-200 rounded-xl">
            <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2">
              <h2 className="text-sm font-semibold">Extracted from listing</h2>
              <span className="source-pill">{sourceLabel(job.source)}</span>
            </div>
            <div className="p-4 text-sm space-y-4">
              {job.extracted.summary && (
                <p className="text-zinc-600 leading-relaxed">{job.extracted.summary}</p>
              )}

              {job.extracted.required_skills.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                    Required skills
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {job.extracted.required_skills.map(skill => (
                      <span key={skill} className={`skill-tag ${getSkillVariant(skill)}`}>
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {job.extracted.preferred_skills.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                    Preferred skills
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {job.extracted.preferred_skills.map(skill => (
                      <span key={skill} className={`skill-tag skill-gen`}>
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(salaryText || locationText) && (
                <div className="flex items-center gap-6">
                  {salaryText && (
                    <div>
                      <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
                        Salary (extracted)
                      </div>
                      <div className="num font-semibold text-zinc-800">{salaryText}</div>
                    </div>
                  )}
                  {locationText && (
                    <div>
                      <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
                        Work arrangement
                      </div>
                      <div className="text-sm text-zinc-700">{locationText}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Generation panel */}
        <GenerationPanel jobId={id} />

      </div>
    </>
  )
}
