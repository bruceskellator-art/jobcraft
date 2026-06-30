'use client'

import { useState, useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import type { ScrapeRunView, ScrapeRunStatus } from '@/lib/api'
import { listScrapeRuns } from '@/lib/api'
import { animateBar } from '@/lib/motion'
import { relativeTime } from '@/lib/relativeTime'
import { sourceLabel } from '@/lib/sources'

/** Fetch coverage as a 0–100 percentage, presentational only. */
function fetchProgressPercent(totalFetched: number, totalListed: number): number {
  if (totalListed <= 0) return 0
  return Math.min(100, Math.round((totalFetched / totalListed) * 100))
}

const MAX_COMPANIES_SHOWN = 3

const POLL_INTERVAL_MS = 3000

interface StatusPillProps {
  status: ScrapeRunStatus
}

function StatusPill({ status }: StatusPillProps) {
  if (status === 'pending') {
    return (
      <span className="badge" style={{ background: 'var(--neutral-bg)', color: 'var(--neutral-fg)' }}>
        <span className="dot" style={{ background: 'var(--muted-foreground)' }} />
        Queued
      </span>
    )
  }
  if (status === 'running') {
    return (
      <span className="badge" style={{ background: 'var(--blue-bg)', color: 'var(--blue-fg)' }}>
        <Loader2 className="w-3 h-3 animate-spin" />
        Running
      </span>
    )
  }
  if (status === 'succeeded') {
    return (
      <span className="badge" style={{ background: 'var(--green-bg)', color: 'var(--green-fg)' }}>
        <span className="dot" style={{ background: 'var(--green-fg)' }} />
        Done
      </span>
    )
  }
  // failed
  return (
    <span className="badge" style={{ background: 'var(--red-bg)', color: 'var(--red-fg)' }}>
      <span className="dot" style={{ background: 'var(--red-fg)' }} />
      Failed
    </span>
  )
}

function companiesSummary(companies: string[]): string {
  const noun = companies.length === 1 ? 'company' : 'companies'
  const shown = companies.slice(0, MAX_COMPANIES_SHOWN).join(', ')
  const ellipsis = companies.length > MAX_COMPANIES_SHOWN ? '…' : ''
  return `${companies.length} ${noun} (${shown}${ellipsis})`
}

function requestSummary(request: ScrapeRunView['request']): string {
  if (!request) return 'No request details'
  const query = request.query?.trim() ?? ''
  const companies = request.companies ?? []
  const parts: string[] = []
  if (query) {
    parts.push(`"${query}" · LinkedIn + MyCareersFuture`)
  }
  if (companies.length > 0) {
    parts.push(companiesSummary(companies))
  }
  return parts.length > 0 ? parts.join(' · ') : 'No sources configured'
}

interface RunCardProps {
  run: ScrapeRunView
}

function RunCard({ run }: RunCardProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Width signature changes as poll updates advance fetch counts; replays the
  // bar growth so progress reads as live without thrashing layout.
  const progressSignature = (run.runs ?? [])
    .map((s) => fetchProgressPercent(s.total_fetched, s.total_listed))
    .join(',')

  useGSAP(
    () => {
      if (!containerRef.current) return
      animateBar(
        gsap.utils.toArray<HTMLElement>('[data-bar]', containerRef.current),
        { stagger: 0.06 },
      )
    },
    { scope: containerRef, dependencies: [progressSignature], revertOnUpdate: true },
  )

  return (
    <div ref={containerRef} className="bg-card border border-border rounded-xl p-4 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <StatusPill status={run.status} />
          {run.status === 'succeeded' && run.total_created > 0 && (
            <span className="text-sm font-semibold" style={{ color: 'var(--green-fg)' }}>
              {run.total_created} new job{run.total_created !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {run.created_at && (
          <span className="text-xs text-muted-foreground shrink-0">
            {relativeTime(run.created_at)}
          </span>
        )}
      </div>

      <p className="text-xs text-muted-foreground truncate">
        {requestSummary(run.request)}
      </p>

      {run.runs && run.runs.length > 0 && (
        <div className="space-y-1 pt-1">
          {run.runs.map(source => {
            const progress = fetchProgressPercent(source.total_fetched, source.total_listed)
            const barColor = source.error
              ? 'var(--red-fg)'
              : run.status === 'succeeded'
                ? 'var(--green-fg)'
                : 'var(--blue-fg)'
            return (
              <div key={source.source}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-foreground font-medium">{sourceLabel(source.source)}</span>
                  <span className="text-muted-foreground">
                    {source.total_new} new / {source.total_listed} listed
                  </span>
                </div>
                {source.total_listed > 0 && (
                  <div className="mt-1 h-1 rounded-full bg-muted overflow-hidden">
                    <div
                      data-bar
                      className="h-full rounded-full"
                      style={{ width: `${progress}%`, background: barColor }}
                    />
                  </div>
                )}
                {source.error && (
                  <p className="text-xs text-destructive mt-0.5">{source.error}</p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {run.error && (
        <p className="text-xs text-destructive">{run.error}</p>
      )}
    </div>
  )
}

export function ScrapingRuns() {
  const [runs, setRuns] = useState<ScrapeRunView[]>([])

  useEffect(() => {
    const controller = new AbortController()

    function fetchRuns() {
      listScrapeRuns(controller.signal)
        .then(data => {
          if (!controller.signal.aborted) {
            setRuns(data)
          }
        })
        .catch(() => {
          // silently ignore — polling will retry
        })
    }

    fetchRuns()
    const intervalId = setInterval(fetchRuns, POLL_INTERVAL_MS)

    return () => {
      controller.abort()
      clearInterval(intervalId)
    }
  }, [])

  if (runs.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-10 empty">
        No scrape runs yet. Start one from Settings — it runs in the background and
        live progress, with a per-source breakdown, shows up here.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {runs.map(run => (
        <RunCard key={run.id} run={run} />
      ))}
    </div>
  )
}
