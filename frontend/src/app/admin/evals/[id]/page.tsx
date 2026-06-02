'use client'

import { useReducer, useEffect } from 'react'
import Link from 'next/link'
import { use } from 'react'
import type { EvalRun, CaseResult, AssertionResult } from '@/types/eval'
import { getEvalRun } from '@/lib/api'

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; run: EvalRun }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; run: EvalRun }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', run: action.run }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

interface AssertionRowProps {
  assertion: AssertionResult
}

function AssertionRow({ assertion }: AssertionRowProps) {
  return (
    <div
      className={`px-3 py-2 rounded-lg text-xs ${
        assertion.passed
          ? 'bg-emerald-50 border border-emerald-100'
          : 'bg-rose-50 border border-rose-200'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="font-semibold text-zinc-700 source-pill">{assertion.kind}</span>
        <span
          className={`font-semibold ${assertion.passed ? 'text-emerald-600' : 'text-rose-600'}`}
        >
          {assertion.passed ? 'pass' : 'fail'}
        </span>
        <span className="num text-zinc-500">{assertion.score.toFixed(2)}</span>
      </div>
      {assertion.detail && (
        <p className={`mt-1 ${assertion.passed ? 'text-zinc-500' : 'text-rose-700'}`}>
          {assertion.detail}
        </p>
      )}
    </div>
  )
}

interface CaseCardProps {
  caseResult: CaseResult
}

function CaseCard({ caseResult }: CaseCardProps) {
  return (
    <div
      className={`bg-white border rounded-xl p-4 space-y-2 ${
        caseResult.passed ? 'border-zinc-200' : 'border-rose-200'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-700 font-mono">{caseResult.case_id}</span>
        <div className="flex items-center gap-2">
          <span className="num text-sm text-zinc-500">{caseResult.score.toFixed(2)}</span>
          <span className={`badge ${caseResult.passed ? 'badge-submitted' : 'badge-failed'}`}>
            <span
              className={`dot ${caseResult.passed ? 'bg-emerald-500' : 'bg-rose-500'}`}
            />
            {caseResult.passed ? 'pass' : 'fail'}
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        {caseResult.assertions.map((assertion, i) => (
          <AssertionRow key={`${assertion.kind}-${i}`} assertion={assertion} />
        ))}
      </div>
    </div>
  )
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default function EvalRunDetailPage({ params }: PageProps) {
  const { id } = use(params)
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    getEvalRun(id, controller.signal)
      .then((run) => {
        if (!controller.signal.aborted) {
          dispatch({ type: 'fetch_success', run })
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load eval run.'
        dispatch({ type: 'fetch_error', message })
      })
    return () => controller.abort()
  }, [id])

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const run = fetchState.status === 'success' ? fetchState.run : null

  const passRate = run?.aggregate_scores['pass_rate'] ?? 0
  const passedCases = run?.results.filter((r) => r.passed).length ?? 0
  const totalCases = run?.results.length ?? 0

  return (
    <>
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center gap-4 px-6 sticky top-0 z-10">
        <Link
          href="/admin/evals"
          className="text-zinc-400 hover:text-zinc-700 transition-colors text-sm flex items-center gap-1"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
            <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2Z" />
          </svg>
          Evals
        </Link>
        <span className="text-zinc-300">/</span>
        <div>
          <h1 className="text-sm font-semibold">
            {run ? run.suite_name : 'Run detail'}
          </h1>
          {run && (
            <p className="text-xs text-zinc-400">
              {formatDateTime(run.started_at)}
              {run.completed_at ? ` → ${formatDateTime(run.completed_at)}` : ' · running…'}
            </p>
          )}
        </div>
      </header>

      <div className="p-6 space-y-5">
        {isLoading && <div className="empty py-16">Loading run detail…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
          </div>
        )}

        {!isLoading && !loadError && run && (
          <>
            <div className="bg-white border border-zinc-200 rounded-xl p-4 flex items-center gap-6 flex-wrap">
              <div>
                <div className="text-xs text-zinc-500 font-medium">Suite</div>
                <div className="text-sm font-semibold text-zinc-800 mt-0.5">
                  {run.suite_name}
                </div>
              </div>
              {run.prompt_version_id && (
                <div>
                  <div className="text-xs text-zinc-500 font-medium">Prompt version</div>
                  <span className="source-pill mt-0.5 inline-block">{run.prompt_version_id}</span>
                </div>
              )}
              <div>
                <div className="text-xs text-zinc-500 font-medium">Pass rate</div>
                <div className="num text-xl font-semibold mt-0.5">{passRate.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-xs text-zinc-500 font-medium">Cases</div>
                <div className="num text-xl font-semibold mt-0.5">
                  {passedCases}/{totalCases}
                </div>
              </div>
              {Object.entries(run.aggregate_scores)
                .filter(([key]) => key !== 'pass_rate')
                .map(([key, val]) => (
                  <div key={key}>
                    <div className="text-xs text-zinc-500 font-medium">{key}</div>
                    <div className="num text-xl font-semibold mt-0.5">{val.toFixed(2)}</div>
                  </div>
                ))}
            </div>

            {run.results.length === 0 ? (
              <div className="empty py-12">No case results in this run.</div>
            ) : (
              <div className="space-y-3">
                <h2 className="text-sm font-semibold text-zinc-700">
                  Case results ({totalCases})
                </h2>
                {run.results.map((caseResult) => (
                  <CaseCard key={caseResult.case_id} caseResult={caseResult} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
