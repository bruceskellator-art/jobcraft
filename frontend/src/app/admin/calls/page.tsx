'use client'

import { useState, useEffect, useCallback, useReducer } from 'react'
import type { LlmCall, CallCostResponse } from '@/types/observability'
import { listAdminCalls, getCallCost } from '@/lib/api'
import { CallRow } from '@/components/admin/CallRow'
import { StatTile } from '@/components/dashboard/StatTile'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const LIMIT_OPTIONS = [25, 50, 100, 200]

const FLAT_SPARKLINE = [
  { x: 0, y: 16 }, { x: 10, y: 16 }, { x: 20, y: 16 },
  { x: 30, y: 16 }, { x: 40, y: 16 }, { x: 50, y: 16 }, { x: 64, y: 16 },
]

function costSparklinePoints(byDay: CallCostResponse['by_day']): Array<{ x: number; y: number }> {
  if (byDay.length === 0) return FLAT_SPARKLINE
  const maxCost = Math.max(...byDay.map((d) => d.cost_usd), 0.001)
  const step = byDay.length > 1 ? 64 / (byDay.length - 1) : 0
  return byDay.map((d, i) => ({
    x: Math.round(i * step),
    y: Math.round(32 - (d.cost_usd / maxCost) * 28 + 2),
  }))
}

function callsSparklinePoints(byDay: CallCostResponse['by_day']): Array<{ x: number; y: number }> {
  if (byDay.length === 0) return FLAT_SPARKLINE
  const maxCalls = Math.max(...byDay.map((d) => d.calls), 1)
  const step = byDay.length > 1 ? 64 / (byDay.length - 1) : 0
  return byDay.map((d, i) => ({
    x: Math.round(i * step),
    y: Math.round(32 - (d.calls / maxCalls) * 28 + 2),
  }))
}

interface LoadedData {
  calls: LlmCall[]
  costData: CallCostResponse
}

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: LoadedData }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; data: LoadedData }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', data: action.data }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

export default function AdminCallsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })
  const [modelFilter, setModelFilter] = useState('')
  const [limit, setLimit] = useState(50)

  const loadData = useCallback(
    (signal: AbortSignal, model: string, lim: number) => {
      Promise.all([
        listAdminCalls(
          { ...(model ? { model } : {}), limit: lim },
          signal,
        ),
        getCallCost(signal),
      ])
        .then(([callList, cost]) => {
          if (signal.aborted) return
          dispatch({ type: 'fetch_success', data: { calls: callList, costData: cost } })
        })
        .catch((err: unknown) => {
          if (signal.aborted) return
          const message = err instanceof Error ? err.message : 'Failed to load LLM calls.'
          dispatch({ type: 'fetch_error', message })
        })
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    loadData(controller.signal, modelFilter, limit)
    return () => controller.abort()
  }, [loadData, modelFilter, limit])

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const calls = fetchState.status === 'success' ? fetchState.data.calls : []
  const costData = fetchState.status === 'success' ? fetchState.data.costData : null
  const totals = costData?.totals
  const byDay = costData?.by_day ?? []

  return (
    <>
      <header className="h-14 bg-card border-b border-border flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">LLM Calls</h1>
          <p className="text-xs text-muted-foreground">
            Every model call — prompt, response, tokens, latency, cost
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            className="text-xs border border-border rounded-lg px-2 py-1.5 text-muted-foreground w-36"
            placeholder="Filter by model…"
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
          />
          <Select value={String(limit)} onValueChange={(v) => setLimit(Number(v))}>
            <SelectTrigger size="sm" className="text-xs text-muted-foreground">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LIMIT_OPTIONS.map((l) => (
                <SelectItem key={l} value={String(l)}>
                  Last {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      <div className="p-6 space-y-5">
        {/* Stat tiles */}
        <section className="grid grid-cols-4 gap-4">
          <StatTile
            label="Total calls"
            value={totals ? totals.total_calls.toLocaleString() : '—'}
            subLabel={<span className="text-xs text-muted-foreground">all time</span>}
            sparklinePoints={callsSparklinePoints(byDay)}
            sparklineColor="#6366f1"
          />
          <StatTile
            label="Total cost"
            value={totals ? `$${totals.total_cost.toFixed(2)}` : '—'}
            subLabel={<span className="text-xs text-muted-foreground">all time</span>}
            sparklinePoints={costSparklinePoints(byDay)}
            sparklineColor="#f59e0b"
          />
          <StatTile
            label="Avg latency"
            value={totals ? `${(totals.avg_latency_ms / 1000).toFixed(1)}s` : '—'}
            subLabel={<span className="text-xs text-muted-foreground">all time</span>}
            sparklinePoints={FLAT_SPARKLINE}
            sparklineColor="#10b981"
          />
          <StatTile
            label="Error rate"
            value={totals ? `${(totals.error_rate * 100).toFixed(1)}%` : '—'}
            subLabel={<span className="text-xs text-muted-foreground">all time</span>}
            sparklinePoints={FLAT_SPARKLINE}
            sparklineColor="#f43f5e"
          />
        </section>

        {/* Calls table */}
        <section className="bg-card border border-border rounded-xl overflow-hidden">
          {isLoading && <div className="empty py-12">Loading calls…</div>}

          {!isLoading && loadError && (
            <div className="px-4 py-3 text-sm text-red-700 bg-red-50">
              {loadError}
            </div>
          )}

          {!isLoading && !loadError && calls.length === 0 && (
            <div className="empty py-12">No calls found.</div>
          )}

          {!isLoading && !loadError && calls.length > 0 && (
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-muted-foreground text-xs border-b border-border">
                <tr className="text-left">
                  <th className="px-4 py-2.5 font-medium">Time</th>
                  <th className="px-2 py-2.5 font-medium">Prompt version</th>
                  <th className="px-2 py-2.5 font-medium">Model</th>
                  <th className="px-2 py-2.5 font-medium text-right">In / Out tokens</th>
                  <th className="px-2 py-2.5 font-medium text-right">Latency</th>
                  <th className="px-2 py-2.5 font-medium text-right">Cost</th>
                  <th className="px-2 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {calls.map((call) => (
                  <CallRow key={call.id} call={call} />
                ))}
              </tbody>
            </table>
          )}

          <div className="px-4 py-3 border-t border-border text-xs text-muted-foreground">
            Click a row to inspect the full rendered prompt + raw response.
          </div>
        </section>
      </div>
    </>
  )
}
