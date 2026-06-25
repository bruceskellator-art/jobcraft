'use client'

import { useState, useEffect, useCallback, useReducer } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import type { EvalRun } from '@/types/eval'
import { listEvalRuns, runEvalSuite } from '@/lib/api'
import { SuiteCard } from '@/components/admin/SuiteCard'
import { EvalRunRow } from '@/components/admin/EvalRunRow'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const KNOWN_SUITES = ['resume_quality_v1', 'extraction_accuracy_v1', 'match_consistency_v1']

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; runs: EvalRun[] }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; runs: EvalRun[] }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', runs: action.runs }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

function groupBySuite(runs: EvalRun[]): Map<string, EvalRun[]> {
  const map = new Map<string, EvalRun[]>()
  for (const run of runs) {
    const existing = map.get(run.suite_name) ?? []
    map.set(run.suite_name, [...existing, run])
  }
  return map
}

function prevPassRateForRun(run: EvalRun, allRuns: EvalRun[]): number | null {
  const suiteRuns = allRuns
    .filter((r) => r.suite_name === run.suite_name)
    .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
  const idx = suiteRuns.findIndex((r) => r.id === run.id)
  if (idx === -1 || idx + 1 >= suiteRuns.length) return null
  return suiteRuns[idx + 1].aggregate_scores['pass_rate'] ?? null
}

export default function AdminEvalsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })
  const [selectedSuite, setSelectedSuite] = useState(KNOWN_SUITES[0] ?? '')
  const [isRunning, setIsRunning] = useState(false)

  const loadRuns = useCallback(
    (signal: AbortSignal) => {
      listEvalRuns(signal)
        .then((runs) => {
          if (!signal.aborted) {
            dispatch({ type: 'fetch_success', runs })
          }
        })
        .catch((err: unknown) => {
          if (signal.aborted) return
          const message = err instanceof Error ? err.message : 'Failed to load eval runs.'
          dispatch({ type: 'fetch_error', message })
        })
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    loadRuns(controller.signal)
    return () => controller.abort()
  }, [loadRuns])

  async function handleRunSuite() {
    if (isRunning || !selectedSuite) return
    setIsRunning(true)
    try {
      const result = await runEvalSuite(selectedSuite)
      toast.success(
        `Suite "${result.suite_name}" completed — pass rate: ${(result.aggregate_scores['pass_rate'] ?? 0).toFixed(2)}`,
      )
      const controller = new AbortController()
      dispatch({ type: 'fetch_start' })
      loadRuns(controller.signal)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      toast.error(err instanceof Error ? err.message : 'Failed to run suite.')
    } finally {
      setIsRunning(false)
    }
  }

  const runs = fetchState.status === 'success' ? fetchState.runs : []
  const suiteMap = groupBySuite(runs)

  const allSuiteNames = Array.from(
    new Set([...KNOWN_SUITES, ...Array.from(suiteMap.keys())]),
  )

  const suitesWithRuns = allSuiteNames.filter((name) => suiteMap.has(name))
  const failingCount = suitesWithRuns.filter((name) => {
    const latest = suiteMap.get(name)?.[0]
    if (!latest) return false
    const rate = latest.aggregate_scores['pass_rate'] ?? 0
    return rate < 0.7
  }).length

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null

  return (
    <>
      <Toaster />
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Evals</h1>
          <p className="text-xs text-zinc-400">
            Prompt quality over time — CI fails if a suite drops below baseline
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => void handleRunSuite()}
          disabled={isRunning}
        >
          {isRunning ? 'Running…' : 'Run all suites'}
        </button>
      </header>

      <div className="p-6 space-y-5">
        {isLoading && <div className="empty py-16">Loading eval runs…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
            <button
              onClick={() => {
                const controller = new AbortController()
                dispatch({ type: 'fetch_start' })
                loadRuns(controller.signal)
              }}
              className="ml-2 underline text-red-600 hover:text-red-800"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !loadError && (
          <>
            {suitesWithRuns.length > 0 && (
              <section className="grid grid-cols-3 gap-4">
                {suitesWithRuns.map((name) => {
                  const suiteRuns = suiteMap.get(name) ?? []
                  const latestRun = suiteRuns[0]
                  if (!latestRun) return null
                  return (
                    <SuiteCard
                      key={name}
                      suiteName={name}
                      latestRun={latestRun}
                      recentRuns={suiteRuns}
                    />
                  )
                })}
              </section>
            )}

            <section className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
                <h2 className="text-sm font-semibold">Recent runs</h2>
                {failingCount > 0 ? (
                  <span className="text-xs text-rose-600 font-medium">
                    {failingCount} failing suite{failingCount !== 1 ? 's' : ''} need
                    {failingCount === 1 ? 's' : ''} attention
                  </span>
                ) : (
                  <span className="text-xs text-zinc-400">All suites passing</span>
                )}
              </div>

              {runs.length === 0 ? (
                <div className="empty py-12">No eval runs yet.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-zinc-50/80 text-zinc-500 text-xs border-b border-zinc-100">
                    <tr className="text-left">
                      <th className="px-4 py-2.5 font-medium">Suite</th>
                      <th className="px-2 py-2.5 font-medium">Prompt version</th>
                      <th className="px-2 py-2.5 font-medium">Model</th>
                      <th className="px-2 py-2.5 font-medium text-right">Score</th>
                      <th className="px-2 py-2.5 font-medium text-right">Δ vs prev</th>
                      <th className="px-2 py-2.5 font-medium">Result</th>
                      <th className="px-2 py-2.5 font-medium">Started</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100">
                    {runs.map((run) => (
                      <EvalRunRow
                        key={run.id}
                        run={run}
                        prevPassRate={prevPassRateForRun(run, runs)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="bg-white border border-zinc-200 rounded-xl p-4">
              <h2 className="text-sm font-semibold mb-3">Run a suite</h2>
              <div className="flex items-center gap-3">
                <Select value={selectedSuite} onValueChange={(v) => { if (v !== null) setSelectedSuite(v) }}>
                  <SelectTrigger className="text-sm text-zinc-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {allSuiteNames.map((name) => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <button
                  className="btn btn-primary"
                  onClick={() => void handleRunSuite()}
                  disabled={isRunning || !selectedSuite}
                >
                  {isRunning ? 'Running…' : 'Run suite'}
                </button>
              </div>
            </section>
          </>
        )}
      </div>
    </>
  )
}
