'use client'

import { useEffect, useReducer } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import type { LlmCallDetail } from '@/types/observability'
import { getAdminCall } from '@/lib/api'
import { relativeTime } from '@/lib/relativeTime'

function getModelBadgeClass(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('opus')) return 'model-badge model-opus'
  if (m.includes('haiku')) return 'model-badge model-haiku'
  return 'model-badge model-sonnet'
}

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; call: LlmCallDetail }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; call: LlmCallDetail }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', call: action.call }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

export default function CallDetailPage() {
  const params = useParams()
  const id = typeof params.id === 'string' ? params.id : ''
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  useEffect(() => {
    if (!id) return
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })

    getAdminCall(id, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        dispatch({ type: 'fetch_success', call: data })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load call detail.'
        dispatch({ type: 'fetch_error', message })
      })

    return () => controller.abort()
  }, [id])

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const call = fetchState.status === 'success' ? fetchState.call : null

  return (
    <>
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center gap-3 px-6 sticky top-0 z-10">
        <Link href="/admin/calls" className="text-xs text-zinc-400 hover:text-zinc-600">
          ← LLM Calls
        </Link>
        <div className="h-4 w-px bg-zinc-200" />
        <h1 className="text-sm font-semibold">Call Detail</h1>
        {call && (
          <span className={getModelBadgeClass(call.model)}>{call.model}</span>
        )}
      </header>

      <div className="p-6 space-y-5">
        {isLoading && <div className="empty py-16">Loading…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
          </div>
        )}

        {!isLoading && !loadError && call && (
          <>
            {/* Meta row */}
            <div className="bg-white border border-zinc-200 rounded-xl p-4 flex flex-wrap gap-6 text-sm">
              <div>
                <div className="text-xs text-zinc-500 mb-1">Model</div>
                <span className={getModelBadgeClass(call.model)}>{call.model}</span>
              </div>
              <div>
                <div className="text-xs text-zinc-500 mb-1">Prompt version</div>
                <span className="source-pill">{call.prompt_version_id ?? '—'}</span>
              </div>
              <div>
                <div className="text-xs text-zinc-500 mb-1">Tokens</div>
                <span className="num text-xs">{call.input_tokens.toLocaleString()} in / {call.output_tokens.toLocaleString()} out</span>
              </div>
              <div>
                <div className="text-xs text-zinc-500 mb-1">Latency</div>
                <span className="num text-xs">{(call.latency_ms / 1000).toFixed(2)}s</span>
              </div>
              <div>
                <div className="text-xs text-zinc-500 mb-1">Cost</div>
                <span className="num text-xs">${call.cost_usd.toFixed(4)}</span>
              </div>
              <div>
                <div className="text-xs text-zinc-500 mb-1">Called</div>
                <span className="text-xs text-zinc-600">{relativeTime(call.called_at)}</span>
              </div>
              {call.error && (
                <div className="w-full">
                  <div className="text-xs text-zinc-500 mb-1">Error</div>
                  <span className="text-xs text-red-600 font-mono">{call.error}</span>
                </div>
              )}
            </div>

            {/* Rendered prompt */}
            <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-100">
                <h2 className="text-sm font-semibold">Rendered Prompt</h2>
              </div>
              <pre className="p-4 text-xs leading-relaxed overflow-x-auto font-mono whitespace-pre-wrap text-zinc-700">
                {call.rendered_prompt}
              </pre>
            </div>

            {/* Response */}
            <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-100">
                <h2 className="text-sm font-semibold">Response</h2>
              </div>
              <pre className="p-4 text-xs leading-relaxed overflow-x-auto font-mono whitespace-pre-wrap text-zinc-700">
                {call.response}
              </pre>
            </div>

            {/* Parsed response */}
            {call.parsed_response !== null && (
              <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-zinc-100">
                  <h2 className="text-sm font-semibold">Parsed Response</h2>
                </div>
                <pre className="p-4 text-xs leading-relaxed overflow-x-auto font-mono whitespace-pre-wrap text-zinc-700">
                  {JSON.stringify(call.parsed_response, null, 2)}
                </pre>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
