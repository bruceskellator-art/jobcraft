'use client'

import { useEffect, useCallback, useReducer } from 'react'
import Link from 'next/link'
import { StatTile } from '@/components/dashboard/StatTile'
import { TopMatchesList } from '@/components/dashboard/TopMatchesList'
import { QueueHealthPanel } from '@/components/dashboard/QueueHealthPanel'
import { SourcesPanel } from '@/components/dashboard/SourcesPanel'
import { RecentActivity } from '@/components/dashboard/RecentActivity'
import { listJobs, listApplications, getCallCost } from '@/lib/api'
import type { CallCostResponse } from '@/types/observability'

const FLAT_SPARKLINE = [
  { x: 0, y: 16 }, { x: 10, y: 16 }, { x: 20, y: 16 },
  { x: 30, y: 16 }, { x: 40, y: 16 }, { x: 50, y: 16 }, { x: 64, y: 16 },
]

function costSparkline(byDay: CallCostResponse['by_day']): Array<{ x: number; y: number }> {
  if (byDay.length === 0) return FLAT_SPARKLINE
  const maxCost = Math.max(...byDay.map((d) => d.cost_usd), 0.001)
  const step = byDay.length > 1 ? 64 / (byDay.length - 1) : 0
  return byDay.map((d, i) => ({
    x: Math.round(i * step),
    y: Math.round(32 - (d.cost_usd / maxCost) * 28 + 2),
  }))
}

function callsSparkline(byDay: CallCostResponse['by_day']): Array<{ x: number; y: number }> {
  if (byDay.length === 0) return FLAT_SPARKLINE
  const maxCalls = Math.max(...byDay.map((d) => d.calls), 1)
  const step = byDay.length > 1 ? 64 / (byDay.length - 1) : 0
  return byDay.map((d, i) => ({
    x: Math.round(i * step),
    y: Math.round(32 - (d.calls / maxCalls) * 28 + 2),
  }))
}

interface DashboardData {
  jobCount: number | null
  appCount: number | null
  cost: CallCostResponse | null
}

interface DashboardState {
  isLoading: boolean
  data: DashboardData
}

type DashboardAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_done'; data: DashboardData }

const INITIAL_DATA: DashboardData = { jobCount: null, appCount: null, cost: null }

function dashboardReducer(_state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case 'fetch_start':
      return { isLoading: true, data: INITIAL_DATA }
    case 'fetch_done':
      return { isLoading: false, data: action.data }
  }
}

export default function DashboardPage() {
  const [state, dispatch] = useReducer(dashboardReducer, {
    isLoading: true,
    data: INITIAL_DATA,
  })

  const loadData = useCallback((signal: AbortSignal) => {
    // Resilient parallel fetches — one failing call shows '—' without crashing
    Promise.allSettled([
      listJobs(undefined, signal),
      listApplications(undefined, signal),
      getCallCost(signal),
    ]).then(([jobsResult, appsResult, costResult]) => {
      if (signal.aborted) return
      dispatch({
        type: 'fetch_done',
        data: {
          jobCount: jobsResult.status === 'fulfilled' ? jobsResult.value.length : null,
          appCount: appsResult.status === 'fulfilled' ? appsResult.value.length : null,
          cost: costResult.status === 'fulfilled' ? costResult.value : null,
        },
      })
    })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    loadData(controller.signal)
    return () => controller.abort()
  }, [loadData])

  const { isLoading, data } = state
  const totalCost = data.cost?.totals.total_cost ?? null
  const totalCalls = data.cost?.totals.total_calls ?? null
  const byDay = data.cost?.by_day ?? []

  const statTiles = [
    {
      id: 'jobs',
      label: 'Jobs indexed',
      value: data.jobCount !== null ? data.jobCount : '—',
      subLabel: <span className="text-xs text-zinc-400">all sources</span>,
      sparklinePoints: FLAT_SPARKLINE,
      sparklineColor: '#10b981',
    },
    {
      id: 'applications',
      label: 'Applications',
      value: data.appCount !== null ? data.appCount : '—',
      subLabel: <span className="text-xs text-zinc-400">total submitted</span>,
      sparklinePoints: FLAT_SPARKLINE,
      sparklineColor: '#6366f1',
    },
    {
      id: 'llm-calls',
      label: 'LLM calls',
      value: totalCalls !== null ? totalCalls.toLocaleString() : '—',
      subLabel: <span className="text-xs text-zinc-400">all time</span>,
      sparklinePoints: callsSparkline(byDay),
      sparklineColor: '#6366f1',
    },
    {
      id: 'llm-cost',
      label: 'LLM cost',
      value: totalCost !== null ? `$${totalCost.toFixed(2)}` : '—',
      subLabel: <span className="text-xs text-zinc-400">all time</span>,
      sparklinePoints: costSparkline(byDay),
      sparklineColor: '#f59e0b',
    },
  ]

  return (
    <>
      {/* Header */}
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Dashboard</h1>
          <p className="text-xs text-zinc-400">
            {isLoading ? 'Loading…' : 'JobCraft overview'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn btn-ghost">Run scrape</button>
          <Link href="/apply-queue" className="btn btn-primary">
            Review apply queue
          </Link>
        </div>
      </header>

      {/* Body */}
      <div className="p-6 space-y-5">
        {/* Stat tiles */}
        <section className="grid grid-cols-4 gap-4">
          {statTiles.map((tile) => (
            <StatTile
              key={tile.id}
              label={tile.label}
              value={tile.value}
              subLabel={tile.subLabel}
              sparklinePoints={tile.sparklinePoints}
              sparklineColor={tile.sparklineColor}
            />
          ))}
        </section>

        {/* Middle row */}
        <div className="grid grid-cols-3 gap-5">
          <TopMatchesList />
          <div className="space-y-4">
            <QueueHealthPanel />
            <SourcesPanel />
          </div>
        </div>

        {/* Recent activity */}
        <RecentActivity />
      </div>
    </>
  )
}
