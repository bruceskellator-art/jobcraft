'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import type { JobPosting } from '@/types/job'
import type { MatchRead } from '@/types/match'
import { getJob, getJobMatch, queueApply } from '@/lib/api'
import { MatchBreakdown } from '@/components/jobs/MatchBreakdown'
import { GenerationPanel } from '@/components/jobs/GenerationPanel'
import { JobDescription } from '@/components/jobs/JobDescription'
import { getSkillVariant } from '@/components/experience/skillTagHelper'
import { CompanyLogo } from '@/components/common/CompanyLogo'
import { sourceLabel } from '@/lib/sources'

type PageState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; job: JobPosting; match: MatchRead | null }

function formatSalary(min?: number, max?: number): string | null {
  if (!min && !max) return null
  const fmt = (n: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
  if (min && max) return `${fmt(min)} – ${fmt(max)}`
  if (min) return `From ${fmt(min)}`
  if (max) return `Up to ${fmt(max)}`
  return null
}

/** True when the match reflects an empty experience corpus (score 0, no items). */
function isEmptyCorpusMatch(match: MatchRead): boolean {
  return (
    match.overall_score === 0 &&
    match.rationale.toLowerCase().includes('no experience')
  )
}

function LoadingSkeleton() {
  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-10">
        <Link href="/jobs" className="text-muted-foreground hover:text-foreground text-sm">
          ← Jobs
        </Link>
      </header>
      <div className="p-6 space-y-5 max-w-3xl animate-pulse">
        {/* Header meta skeleton */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-muted" />
          <div className="space-y-1.5">
            <div className="h-3.5 w-48 rounded bg-muted" />
            <div className="h-3 w-32 rounded bg-muted" />
          </div>
        </div>
        {/* Match card skeleton */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <div className="h-3.5 w-32 rounded bg-muted" />
            <div className="h-6 w-12 rounded-full bg-muted" />
          </div>
          <div className="p-4 grid grid-cols-2 gap-x-8 gap-y-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-3 w-24 rounded bg-muted" />
                <div className="h-2 w-full rounded-full bg-muted" />
              </div>
            ))}
          </div>
        </div>
        {/* Description skeleton */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <div className="h-3.5 w-36 rounded bg-muted" />
          </div>
          <div className="p-4 space-y-2">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-3 rounded bg-muted" style={{ width: `${70 + (i % 3) * 10}%` }} />
            ))}
          </div>
        </div>
        {/* Generation panel skeleton */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <div className="h-3.5 w-40 rounded bg-muted" />
            <div className="h-3 w-56 rounded bg-muted mt-1" />
          </div>
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="h-9 rounded-lg bg-muted" />
              <div className="h-9 rounded-lg bg-muted" />
            </div>
            <div className="flex gap-2">
              <div className="h-9 flex-1 rounded-lg bg-muted" />
              <div className="h-9 flex-1 rounded-lg bg-muted" />
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default function JobDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id

  const [state, setState] = useState<PageState>({ status: 'loading' })
  const [isScoringMatch, setIsScoringMatch] = useState(false)
  const [isQueueing, setIsQueueing] = useState(false)

  useEffect(() => {
    if (!id) return
    const controller = new AbortController()

    async function load() {
      setState({ status: 'loading' })
      try {
        const job = await getJob(id, controller.signal)
        if (!controller.signal.aborted) {
          // Use the embedded match directly — do NOT auto-call getJobMatch
          setState({ status: 'success', job, match: job.match ?? null })
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

  const handleScoreMatch = useCallback(async () => {
    if (isScoringMatch || state.status !== 'success') return
    setIsScoringMatch(true)
    try {
      const match = await getJobMatch(id)
      setState(prev =>
        prev.status === 'success' ? { ...prev, match } : prev,
      )
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to compute match.')
    } finally {
      setIsScoringMatch(false)
    }
  }, [id, isScoringMatch, state.status])

  const handleQueueApply = useCallback(async () => {
    if (isQueueing) return
    setIsQueueing(true)
    try {
      await queueApply([id])
      toast.success('Added to your apply queue', {
        action: {
          label: 'View applications',
          onClick: () => { window.location.href = '/applications' },
        },
      })
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to queue job.')
    } finally {
      setIsQueueing(false)
    }
  }, [id, isQueueing])

  if (state.status === 'loading') {
    return <LoadingSkeleton />
  }

  if (state.status === 'error') {
    return (
      <>
        <Toaster />
        <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-10">
          <Link href="/jobs" className="text-muted-foreground hover:text-foreground text-sm">
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
      <header className="h-14 bg-card border-b border-border flex items-center justify-between px-6 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <Link href="/jobs" className="text-muted-foreground hover:text-foreground text-sm">
            ← Jobs
          </Link>
          <div className="flex items-center gap-2.5">
            <CompanyLogo company={displayCompany} logoUrl={job.company_logo_url} size="md" />
            <div>
              <h1 className="text-sm font-semibold">{displayTitle}</h1>
              <p className="text-xs text-muted-foreground">
                {displayCompany}
                {locationText ? ` · ${locationText}` : ''}
                {seniority ? ` · ${seniority}` : ''}
                {' · '}
                <span className="source-pill">{sourceLabel(job.source)}</span>
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={job.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost text-xs"
          >
            View original →
          </a>
          <button
            className="btn btn-primary text-xs"
            onClick={() => void handleQueueApply()}
            disabled={isQueueing}
          >
            {isQueueing ? 'Queuing…' : 'Queue for auto-apply'}
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="p-6 space-y-5 max-w-3xl">

        {/* Auto-apply flow explanation */}
        <p className="text-xs text-muted-foreground leading-relaxed">
          Queued jobs enter your Apply pipeline — Autopilot (
          <Link href="/settings" className="underline underline-offset-2 hover:text-foreground">
            Settings
          </Link>
          ) auto-submits high-confidence ones; the rest wait for review on the{' '}
          <Link href="/applications" className="underline underline-offset-2 hover:text-foreground">
            Applications
          </Link>{' '}
          page.
        </p>

        {/* Match breakdown */}
        {match ? (
          <>
            <MatchBreakdown match={match} />
            {isEmptyCorpusMatch(match) && (
              <p className="text-xs text-muted-foreground bg-card border border-border rounded-lg px-3 py-2 leading-relaxed">
                Matching uses your experience — add it in{' '}
                <Link href="/workspace" className="underline underline-offset-2 hover:text-foreground">
                  Workspace
                </Link>{' '}
                (or import a résumé) to get real scores.
              </p>
            )}
          </>
        ) : (
          <section className="bg-card border border-border rounded-xl px-4 py-6 flex flex-col items-center gap-3">
            <p className="text-sm text-muted-foreground text-center">
              This job hasn&apos;t been scored yet.
            </p>
            <button
              className="btn btn-ghost text-sm"
              onClick={() => void handleScoreMatch()}
              disabled={isScoringMatch}
            >
              {isScoringMatch ? (
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"
                    aria-hidden="true"
                  />
                  Scoring…
                </span>
              ) : (
                'Score this job'
              )}
            </button>
          </section>
        )}

        {/* Job description */}
        {job.raw_content && (
          <JobDescription content={job.raw_content} />
        )}

        {/* Extracted from listing */}
        {job.extracted && (
          <section className="bg-card border border-border rounded-xl">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <h2 className="text-sm font-semibold">Extracted from listing</h2>
              <span className="source-pill">{sourceLabel(job.source)}</span>
            </div>
            <div className="p-4 text-sm space-y-4">
              {job.extracted.summary && (
                <p className="text-muted-foreground leading-relaxed">{job.extracted.summary}</p>
              )}

              {job.extracted.required_skills.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
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
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
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
                      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                        Salary (extracted)
                      </div>
                      <div className="num font-semibold text-foreground">{salaryText}</div>
                    </div>
                  )}
                  {locationText && (
                    <div>
                      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                        Work arrangement
                      </div>
                      <div className="text-sm text-foreground">{locationText}</div>
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
