'use client'

import { useEffect, useCallback, useReducer } from 'react'
import Link from 'next/link'
import type { PromptVersion } from '@/types/observability'
import { listPrompts } from '@/lib/api'

function getModelBadgeClass(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('opus')) return 'model-badge model-opus'
  if (m.includes('haiku')) return 'model-badge model-haiku'
  return 'model-badge model-sonnet'
}

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; grouped: Record<string, PromptVersion[]> }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; grouped: Record<string, PromptVersion[]> }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', grouped: action.grouped }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

export default function AdminPromptsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  const loadData = useCallback((signal: AbortSignal) => {
    listPrompts(signal)
      .then((data) => {
        if (signal.aborted) return
        dispatch({ type: 'fetch_success', grouped: data })
      })
      .catch((err: unknown) => {
        if (signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load prompts.'
        dispatch({ type: 'fetch_error', message })
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    loadData(controller.signal)
    return () => controller.abort()
  }, [loadData])

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const grouped = fetchState.status === 'success' ? fetchState.grouped : {}
  const promptNames = Object.keys(grouped).sort()

  return (
    <>
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Prompts</h1>
          <p className="text-xs text-zinc-400">
            Versioned templates — diff, eval, then promote the active version
          </p>
        </div>
      </header>

      <div className="p-6">
        {isLoading && <div className="empty py-16">Loading prompts…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
            <button
              onClick={() => {
                const controller = new AbortController()
                dispatch({ type: 'fetch_start' })
                loadData(controller.signal)
              }}
              className="ml-2 underline text-red-600 hover:text-red-800"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !loadError && promptNames.length === 0 && (
          <div className="empty py-16">No prompts found.</div>
        )}

        {!isLoading && !loadError && promptNames.length > 0 && (
          <div className="space-y-5">
            {promptNames.map((name) => {
              const versions = [...(grouped[name] ?? [])].sort((a, b) => b.version - a.version)
              return (
                <section key={name} className="bg-white border border-zinc-200 rounded-xl self-start">
                  <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-2">
                    <h2 className="text-sm font-semibold">{name}</h2>
                    <span className="source-pill">
                      {versions.length} version{versions.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <ul className="divide-y divide-zinc-100">
                    {versions.map((v) => (
                      <li key={v.id}>
                        <Link
                          href={`/admin/prompts/${v.id}`}
                          className="data-row px-4 py-3 flex items-center justify-between hover:bg-zinc-50"
                          style={v.is_active ? { background: '#f0fdf4' } : {}}
                        >
                          <div className="flex items-center gap-2.5">
                            <span className={`num font-semibold ${v.is_active ? 'text-zinc-800' : 'text-zinc-500'}`}>
                              v{v.version}
                            </span>
                            <div>
                              <span className={getModelBadgeClass(v.model)}>{v.model}</span>
                              <span className="text-xs text-zinc-400 ml-1">temp {v.temperature}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {v.is_active && (
                              <span className="badge badge-submitted">
                                <span className="dot" style={{ background: '#10b981' }} />
                                active
                              </span>
                            )}
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
