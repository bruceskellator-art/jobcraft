'use client'

import { useState, useEffect, useReducer, useCallback } from 'react'
import { toast } from 'sonner'
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

export function ApplyQueueView() {
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
      {/* Toolbar row — bulk approve button lives here, right-aligned */}
      {!isLoading && !loadError && highConfCount > 0 && (
        <div className="flex justify-end px-6 pt-4">
          <button
            className="btn btn-primary"
            onClick={() => void handleBulkApprove()}
            disabled={isBulkApproving}
          >
            {isBulkApproving ? 'Approving…' : `Approve all high-confidence · ${highConfCount}`}
          </button>
        </div>
      )}

      {autopilot && autopilot.mode !== 'off' && (
        <div
          className="mx-6 mt-4 rounded-lg border px-4 py-2.5 text-xs flex items-center gap-2"
          style={{
            background: 'var(--green-bg)',
            borderColor: 'color-mix(in srgb, var(--green-fg) 30%, transparent)',
            color: 'var(--green-fg)',
          }}
        >
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-semibold"
            style={{ background: 'var(--green-fg)', color: 'var(--green-bg)' }}
          >
            autopilot {autopilot.mode}
          </span>
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
          <div className="col-span-3 bg-card border border-border rounded-xl overflow-hidden">
            {queue.length === 0 ? (
              <div className="empty py-16">Queue is empty — nothing to apply.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-muted/80 text-muted-foreground text-xs border-b border-border">
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
                <tbody className="divide-y divide-border">
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
              <div className="bg-card border border-border rounded-xl">
                <div className="empty py-24">Select a job to review</div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
