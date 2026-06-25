'use client'

import { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import type { ScrapeRunView, ScrapeRunStatus } from '@/lib/api'
import { listScrapeRuns } from '@/lib/api'
import { relativeTime } from '@/lib/relativeTime'

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

function requestSummary(request: ScrapeRunView['request']): string {
  if (!request) return 'No request details'
  const parts: string[] = []
  if (request.linkedin_keywords?.length) {
    parts.push(`LinkedIn: ${request.linkedin_keywords.join(', ')}`)
  }
  if (request.mcf_keywords?.length) {
    parts.push(`MCF: ${request.mcf_keywords.join(', ')}`)
  }
  if (request.greenhouse_boards?.length) {
    parts.push(`${request.greenhouse_boards.length} Greenhouse board${request.greenhouse_boards.length !== 1 ? 's' : ''}`)
  }
  if (request.lever_companies?.length) {
    parts.push(`${request.lever_companies.length} Lever compan${request.lever_companies.length !== 1 ? 'ies' : 'y'}`)
  }
  return parts.length > 0 ? parts.join(' · ') : 'No sources configured'
}

interface RunCardProps {
  run: ScrapeRunView
}

function RunCard({ run }: RunCardProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-2">
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
          {run.runs.map(source => (
            <div key={source.source}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-foreground font-medium">{source.source}</span>
                <span className="text-muted-foreground">
                  {source.total_new} new / {source.total_listed} listed
                </span>
              </div>
              {source.error && (
                <p className="text-xs text-destructive mt-0.5">{source.error}</p>
              )}
            </div>
          ))}
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
