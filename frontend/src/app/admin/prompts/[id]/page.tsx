'use client'

import { useEffect, useReducer } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import type { PromptDetail } from '@/types/observability'
import { getPrompt } from '@/lib/api'

function getModelBadgeClass(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('opus')) return 'model-badge model-opus'
  if (m.includes('haiku')) return 'model-badge model-haiku'
  return 'model-badge model-sonnet'
}

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; prompt: PromptDetail }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; prompt: PromptDetail }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', prompt: action.prompt }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

export default function PromptDetailPage() {
  const params = useParams()
  const id = typeof params.id === 'string' ? params.id : ''
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  useEffect(() => {
    if (!id) return
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })

    getPrompt(id, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        dispatch({ type: 'fetch_success', prompt: data })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load prompt detail.'
        dispatch({ type: 'fetch_error', message })
      })

    return () => controller.abort()
  }, [id])

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const prompt = fetchState.status === 'success' ? fetchState.prompt : null

  return (
    <>
      <header className="h-14 bg-card border-b border-border flex items-center gap-3 px-6 sticky top-0 z-10">
        <Link href="/admin/prompts" className="text-xs text-muted-foreground hover:text-muted-foreground">
          ← Prompts
        </Link>
        <div className="h-4 w-px bg-border" />
        <h1 className="text-sm font-semibold">Prompt Detail</h1>
        {prompt && (
          <>
            <span className="text-xs text-muted-foreground">{prompt.name}</span>
            <span className="num text-xs text-muted-foreground">v{prompt.version}</span>
          </>
        )}
      </header>

      <div className="p-6 space-y-5">
        {isLoading && <div className="empty py-16">Loading…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
          </div>
        )}

        {!isLoading && !loadError && prompt && (
          <>
            {/* Meta */}
            <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap gap-6 text-sm">
              <div>
                <div className="text-xs text-muted-foreground mb-1">Name</div>
                <span className="text-sm font-semibold">{prompt.name}</span>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Version</div>
                <span className="num font-semibold">v{prompt.version}</span>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Model</div>
                <span className={getModelBadgeClass(prompt.model)}>{prompt.model}</span>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Temperature</div>
                <span className="num text-xs">{prompt.temperature}</span>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Status</div>
                {prompt.is_active ? (
                  <span className="badge badge-submitted">
                    <span className="dot" style={{ background: '#10b981' }} />
                    active
                  </span>
                ) : (
                  <span className="badge badge-queued">inactive</span>
                )}
              </div>
            </div>

            {/* Template */}
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h2 className="text-sm font-semibold">Template</h2>
              </div>
              <pre className="p-4 text-xs leading-relaxed overflow-x-auto font-mono whitespace-pre-wrap text-foreground">
                {prompt.template}
              </pre>
            </div>

            {/* Metadata */}
            {Object.keys(prompt.metadata).length > 0 && (
              <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-border">
                  <h2 className="text-sm font-semibold">Metadata</h2>
                </div>
                <pre className="p-4 text-xs leading-relaxed overflow-x-auto font-mono whitespace-pre-wrap text-foreground">
                  {JSON.stringify(prompt.metadata, null, 2)}
                </pre>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
