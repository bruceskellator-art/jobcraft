'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { listApplications } from '@/lib/api'
import { animateBar } from '@/lib/motion'
import type { Application } from '@/types/apply'

interface QueueCounts {
  autoSubmitted: number
  needsReview: number
  blocked: number
}

interface QueueRow {
  label: string
  badgeClass: string
  dotColor: string
  color: string
  count: number
}

const ZERO_COUNTS: QueueCounts = { autoSubmitted: 0, needsReview: 0, blocked: 0 }

function deriveCounts(apps: Application[]): QueueCounts {
  return apps.reduce<QueueCounts>((acc, app) => {
    if (app.status === 'submitted' && app.apply_mode === 'auto') {
      return { ...acc, autoSubmitted: acc.autoSubmitted + 1 }
    }
    if (app.status === 'review') {
      return { ...acc, needsReview: acc.needsReview + 1 }
    }
    if (app.status === 'blocked') {
      return { ...acc, blocked: acc.blocked + 1 }
    }
    return acc
  }, ZERO_COUNTS)
}

function buildRows(counts: QueueCounts): QueueRow[] {
  return [
    {
      label: 'Auto-submitted',
      badgeClass: 'badge badge-submitted',
      dotColor: 'bg-emerald-500',
      color: '#10b981',
      count: counts.autoSubmitted,
    },
    {
      label: 'Needs review',
      badgeClass: 'badge badge-review',
      dotColor: 'bg-amber-500',
      color: '#f59e0b',
      count: counts.needsReview,
    },
    {
      label: 'Blocked',
      badgeClass: 'badge badge-blocked',
      dotColor: 'bg-rose-500',
      color: '#f43f5e',
      count: counts.blocked,
    },
  ]
}

export function QueueHealthPanel() {
  const containerRef = useRef<HTMLElement>(null)
  const [counts, setCounts] = useState<QueueCounts>(ZERO_COUNTS)

  // Animate bar widths from 0 once counts arrive (and again if they change).
  useGSAP(
    () => {
      if (!containerRef.current) return
      animateBar(
        gsap.utils.toArray<HTMLElement>('[data-bar]', containerRef.current),
        { stagger: 0.08, delay: 0.35 },
      )
    },
    { scope: containerRef, dependencies: [counts], revertOnUpdate: true },
  )

  useEffect(() => {
    const controller = new AbortController()
    listApplications(undefined, controller.signal)
      .then((apps) => {
        if (controller.signal.aborted) return
        setCounts(deriveCounts(apps))
      })
      .catch(() => {
        // leave zeros — one failing call shouldn't crash the dashboard
      })
    return () => controller.abort()
  }, [])

  const rows = buildRows(counts)
  const maxCount = Math.max(counts.autoSubmitted, counts.needsReview, counts.blocked)

  return (
    <section ref={containerRef} className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">Apply queue health</h2>
        <Link href="/apply-queue" className="text-xs font-medium text-primary hover:underline">
          Open →
        </Link>
      </div>
      <div className="p-4 space-y-3 text-sm">
        {rows.map((row) => {
          const widthPercent = maxCount > 0 ? Math.round((row.count / maxCount) * 100) : 0
          return (
            <div key={row.label} className="flex items-center gap-2.5">
              <span className={`${row.badgeClass} text-xs w-28 flex-none px-2.5 py-1`}>
                <span className={`dot ${row.dotColor}`} />
                {row.label}
              </span>
              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  data-bar
                  className="h-full rounded-full"
                  style={{ width: `${widthPercent}%`, background: row.color }}
                />
              </div>
              <span className="num text-xs text-muted-foreground w-4 text-right">
                {row.count}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
