'use client'

import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import type { StatusEvent } from '@/types/email'
import {
  listProposedStatusEvents,
  confirmStatusEvent,
  dismissStatusEvent,
} from '@/lib/api'
import { scoreColor } from '@/lib/scoreColor'

// ---------------------------------------------------------------------------
// Single event row
// ---------------------------------------------------------------------------

interface EventRowProps {
  event: StatusEvent
  onConfirm: (id: string) => Promise<void>
  onDismiss: (id: string) => Promise<void>
  processingId: string | null
}

function StatusArrow({ from, to }: { from: string | null; to: string }) {
  const label = (s: string) =>
    s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <span className="text-xs text-zinc-600 font-medium">
      {from ? (
        <>
          <span className="text-zinc-400">{label(from)}</span>
          <span className="mx-1.5 text-zinc-300">→</span>
          <span className="text-zinc-800">{label(to)}</span>
        </>
      ) : (
        <span className="text-zinc-800">{label(to)}</span>
      )}
    </span>
  )
}

function EventRow({
  event,
  onConfirm,
  onDismiss,
  processingId,
}: EventRowProps) {
  const isProcessing = processingId === event.id
  const chipClass = scoreColor(event.confidence)

  // Offer and rejected are high-stakes: highlight them
  const isHighStakes =
    event.to_status === 'offer' || event.to_status === 'rejected'

  return (
    <div
      className={`flex items-center justify-between gap-4 px-4 py-3 ${
        isHighStakes ? 'bg-amber-50' : ''
      }`}
    >
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusArrow from={event.from_status} to={event.to_status} />
          {isHighStakes && (
            <span className="badge badge-review text-[0.65rem] px-1.5 py-0.5">
              <span className="dot bg-amber-500" />
              review required
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-400">{event.classification}</span>
          <span className={`chip ${chipClass}`}>
            {event.confidence.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-none">
        <button
          className="btn btn-primary text-xs"
          onClick={() => { void onConfirm(event.id) }}
          disabled={isProcessing}
        >
          {isProcessing ? '…' : 'Confirm'}
        </button>
        <button
          className="btn btn-ghost text-xs"
          onClick={() => { void onDismiss(event.id) }}
          disabled={isProcessing}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProposedEvents panel — main export
// ---------------------------------------------------------------------------

interface ProposedEventsProps {
  onBoardRefresh: () => void
}

export function ProposedEvents({ onBoardRefresh }: ProposedEventsProps) {
  const [events, setEvents] = useState<StatusEvent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [processingId, setProcessingId] = useState<string | null>(null)

  const loadEvents = useCallback((signal: AbortSignal) => {
    listProposedStatusEvents(signal)
      .then((data) => {
        if (signal.aborted) return
        setEvents(data)
        setIsLoading(false)
      })
      .catch((err: unknown) => {
        if (signal.aborted) return
        // Non-critical: show a toast so the board still renders without a hard error state
        const message = err instanceof Error ? err.message : 'Failed to load suggested updates.'
        toast.error(message)
        setIsLoading(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadEvents(controller.signal)
    return () => controller.abort()
  }, [loadEvents])

  async function handleConfirm(id: string) {
    if (processingId !== null) return
    setProcessingId(id)
    try {
      await confirmStatusEvent(id)
      setEvents((prev) => prev.filter((e) => e.id !== id))
      toast.success('Status update confirmed and applied.')
      onBoardRefresh()
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to confirm event.')
    } finally {
      setProcessingId(null)
    }
  }

  async function handleDismiss(id: string) {
    if (processingId !== null) return
    setProcessingId(id)
    try {
      await dismissStatusEvent(id)
      setEvents((prev) => prev.filter((e) => e.id !== id))
      toast.success('Suggestion dismissed.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to dismiss event.')
    } finally {
      setProcessingId(null)
    }
  }

  // Nothing to show while loading or when empty
  if (isLoading || events.length === 0) return null

  return (
    <div className="mb-5 bg-white border border-indigo-200 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 bg-indigo-50 border-b border-indigo-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="col-dot" style={{ background: '#6366f1' }} />
          <span className="text-xs font-semibold text-indigo-800">
            Suggested updates
          </span>
          <span className="num text-xs text-indigo-600 bg-indigo-100 px-1.5 py-0.5 rounded-full">
            {events.length}
          </span>
        </div>
        <p className="text-xs text-indigo-500">
          Detected from your email — confirm or dismiss each one.
        </p>
      </div>

      <div className="divide-y divide-zinc-100">
        {events.map((event) => (
          <EventRow
            key={event.id}
            event={event}
            onConfirm={handleConfirm}
            onDismiss={handleDismiss}
            processingId={processingId}
          />
        ))}
      </div>
    </div>
  )
}
