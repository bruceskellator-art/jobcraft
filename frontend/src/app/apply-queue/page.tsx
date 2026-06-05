'use client'

import { useState, useEffect, useReducer, useCallback } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import type { ApplyQueueItem, AutopilotConfig } from '@/types/apply'
import { getApplyQueue, getAutopilot, approveApplication } from '@/lib/api'
import { QueueRow } from '@/components/apply/QueueRow'
import { FieldMapReview } from '@/components/apply/FieldMapReview'
import { Checkbox } from '@/components/ui/checkbox'

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; queue: ApplyQueueItem[] }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; queue: ApplyQueueItem[] }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', queue: action.queue }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

function isHighConfidenceNoKnockout(item: ApplyQueueItem): boolean {
  const conf = item.field_map?.overall_confidence ?? item.application.apply_confidence
  if (conf < 0.7) return false
  if (!item.field_map) return false
  return !item.field_map.fields.some(f => f.field.is_knockout && f.value === null)
}

export default function ApplyQueuePage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())
  const [isApproving, setIsApproving] = useState(false)
  const [isBulkApproving, setIsBulkApproving] = useState(false)
  const [autopilot, setAutopilot] = useState<AutopilotConfig | null>(null)

  const loadQueue = useCallback((signal: AbortSignal) => {
    Promise.all([
      getApplyQueue(signal),
      getAutopilot(signal).catch(() => null),
    ])
      .then(([queue, ap]) => {
        if (signal.aborted) return
        dispatch({ type: 'fetch_success', queue })
        setAutopilot(ap)
        setSelectedId(prev => prev ?? (queue[0]?.application.id ?? null))
      })
      .catch((err: unknown) => {
        if (signal.aborted) return
        dispatch({
          type: 'fetch_error',
          message: err instanceof Error ? err.message : 'Failed to load queue.',
        })
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    loadQueue(controller.signal)
    return () => controller.abort()
  }, [loadQueue])

  const queue = fetchState.status === 'success' ? fetchState.queue : []
  const selectedItem = queue.find(i => i.application.id === selectedId) ?? null
  const highConfCount = queue.filter(isHighConfidenceNoKnockout).length

  async function handleApprove() {
    if (isApproving || !selectedId) return
    setIsApproving(true)
    try {
      await approveApplication(selectedId)
      toast.success('Approved and submitted.')
      const controller = new AbortController()
      dispatch({ type: 'fetch_start' })
      loadQueue(controller.signal)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to approve.')
    } finally {
      setIsApproving(false)
    }
  }

  function handleSkip() {
    const idx = queue.findIndex(i => i.application.id === selectedId)
    const next = queue[idx + 1] ?? queue[idx - 1]
    setSelectedId(next?.application.id ?? null)
  }

  async function handleBulkApprove() {
    if (isBulkApproving) return
    const eligible = queue.filter(isHighConfidenceNoKnockout)
    if (eligible.length === 0) return
    setIsBulkApproving(true)
    try {
      await Promise.all(eligible.map(i => approveApplication(i.application.id)))
      toast.success(`Approved ${eligible.length} application${eligible.length !== 1 ? 's' : ''}.`)
      const controller = new AbortController()
      dispatch({ type: 'fetch_start' })
      loadQueue(controller.signal)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Bulk approve failed.')
    } finally {
      setIsBulkApproving(false)
    }
  }

  function handleCheckAll(checked: boolean) {
    if (checked) {
      setCheckedIds(new Set(queue.map(i => i.application.id)))
    } else {
      setCheckedIds(new Set())
    }
  }

  function handleCheck(id: string, checked: boolean) {
    setCheckedIds(prev => {
      const next = new Set(prev)
      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const allChecked = queue.length > 0 && checkedIds.size === queue.length

  return (
    <>
      <Toaster />
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Apply Queue</h1>
          <p className="text-xs text-zinc-400">
            {isLoading ? 'Loading…' : loadError ? 'Error' : `${queue.length} pending`}
          </p>
        </div>
        {!isLoading && !loadError && highConfCount > 0 && (
          <button
            className="btn btn-primary"
            onClick={() => void handleBulkApprove()}
            disabled={isBulkApproving}
          >
            {isBulkApproving ? 'Approving…' : `Approve all high-confidence · ${highConfCount}`}
          </button>
        )}
      </header>

      {autopilot && autopilot.mode !== 'off' && (
        <div className="bg-emerald-50 border-b border-emerald-200 px-6 py-2 text-xs text-emerald-700 flex items-center gap-2">
          <span className="toggle-on">autopilot {autopilot.mode}</span>
          <span>
            Sources: {autopilot.auto_submit_sources.join(', ') || 'none'} · min confidence{' '}
            {Math.round(autopilot.min_confidence * 100)}%
          </span>
        </div>
      )}

      {isLoading && <div className="empty py-16">Loading queue…</div>}

      {!isLoading && loadError && (
        <div className="m-6 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          {loadError}
          <button
            onClick={() => {
              const controller = new AbortController()
              dispatch({ type: 'fetch_start' })
              loadQueue(controller.signal)
            }}
            className="ml-2 underline text-red-600 hover:text-red-800"
          >
            Retry
          </button>
        </div>
      )}

      {!isLoading && !loadError && (
        <div className="p-6 grid grid-cols-5 gap-4 items-start">
          {/* Queue list — 3 cols */}
          <div className="col-span-3 bg-white border border-zinc-200 rounded-xl overflow-hidden">
            {queue.length === 0 ? (
              <div className="empty py-16">Queue is empty — nothing to apply.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-zinc-50/80 text-zinc-500 text-xs border-b border-zinc-100">
                  <tr className="text-left">
                    <th className="px-3 py-2.5 w-8">
                      <Checkbox
                        checked={allChecked}
                        onCheckedChange={handleCheckAll}
                      />
                    </th>
                    <th className="px-3 py-2.5 font-medium">Role / Company</th>
                    <th className="px-3 py-2.5 font-medium w-12">Fit</th>
                    <th className="px-3 py-2.5 font-medium w-16">Conf.</th>
                    <th className="px-3 py-2.5 font-medium w-24">State</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {queue.map(item => (
                    <QueueRow
                      key={item.application.id}
                      item={item}
                      isSelected={item.application.id === selectedId}
                      isChecked={checkedIds.has(item.application.id)}
                      onSelect={() => setSelectedId(item.application.id)}
                      onCheck={checked => handleCheck(item.application.id, checked)}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Review card — 2 cols */}
          <div className="col-span-2">
            {selectedItem ? (
              <FieldMapReview
                item={selectedItem}
                onApprove={() => void handleApprove()}
                onSkip={handleSkip}
                isApproving={isApproving}
              />
            ) : (
              <div className="bg-white border border-zinc-200 rounded-xl">
                <div className="empty py-24">Select a job to review</div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
