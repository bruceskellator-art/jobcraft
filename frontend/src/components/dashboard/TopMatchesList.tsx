'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { CompanyLogo } from '@/components/common/CompanyLogo'
import { listJobs } from '@/lib/api'
import { sourceLabel } from '@/lib/sources'
import { relativeTime } from '@/lib/relativeTime'
import type { JobPosting } from '@/types/job'

const TOP_MATCHES_LIMIT = 5

function fitChipVariant(score: number): string {
  if (score >= 0.75) return 'chip-high'
  if (score >= 0.5) return 'chip-mid'
  return 'chip-low'
}

export function TopMatchesList() {
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    listJobs({ sort: 'fit', scored: true, limit: TOP_MATCHES_LIMIT }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setJobs(page.items)
        setIsLoading(false)
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setIsLoading(false)
      })
    return () => controller.abort()
  }, [])

  return (
    <section data-animate className="col-span-2 bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">Top new matches today</h2>
        <Link href="/jobs" className="text-xs font-medium text-primary hover:underline">
          See all →
        </Link>
      </div>

      {isLoading ? (
        <div className="empty py-10 px-4">Loading matches…</div>
      ) : jobs.length === 0 ? (
        <div className="empty py-10 px-4">No matches yet — run a scrape and score jobs</div>
      ) : (
        <div className="divide-y divide-border">
          {jobs.map((job) => {
            const score = job.match?.overall_score ?? 0
            return (
              <div key={job.id} className="flex items-center gap-3 px-4 py-3 data-row">
                <CompanyLogo company={job.company} logoUrl={job.company_logo_url} size="sm" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-foreground truncate">{job.title}</div>
                  <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
                    <span className="truncate">{job.company}</span>
                    <span className="source-pill ml-0.5">{sourceLabel(job.source)}</span>
                  </div>
                </div>
                <div className="text-xs text-muted-foreground w-12 text-right num flex-none">
                  {relativeTime(job.scraped_at)}
                </div>
                <span className={`chip ${fitChipVariant(score)} flex-none`}>{score.toFixed(2)}</span>
                <Link
                  href={`/jobs/${job.id}`}
                  className="btn btn-ghost text-xs flex-none cursor-pointer"
                >
                  View
                </Link>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
