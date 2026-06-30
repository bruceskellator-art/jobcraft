'use client'

import { useEffect, useCallback, useReducer } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import type { JobPosting } from '@/types/job'
import { listApplications, listJobs, updateApplicationStatus } from '@/lib/api'
import { KanbanColumn } from '@/components/applications/KanbanColumn'
import type { ApplicationCardData } from '@/components/applications/ApplicationCard'
import { ProposedEvents } from '@/components/applications/ProposedEvents'
import { useEntrance } from '@/hooks/useEntrance'
import { MOTION } from '@/lib/motion'

interface Column {
  id: string
  label: string
  dotColor: string
  countColor: string
  countBg: string
  statuses: string[]
}

const COLUMNS: Column[] = [
  {
    id: 'submitted',
    label: 'Submitted',
    dotColor: '#a1a1aa',
    countColor: '#71717a',
    countBg: '#f4f4f5',
    statuses: ['submitted'],
  },
  {
    id: 'phone_screen',
    label: 'Phone Screen',
    dotColor: '#f59e0b',
    countColor: '#b45309',
    countBg: '#fffbeb',
    statuses: ['phone_screen'],
  },
  {
    id: 'technical_onsite',
    label: 'Technical',
    dotColor: '#6366f1',
    countColor: '#4338ca',
    countBg: '#eef2ff',
    statuses: ['technical', 'onsite'],
  },
  {
    id: 'offer',
    label: 'Offer',
    dotColor: '#10b981',
    countColor: '#047857',
    countBg: '#ecfdf5',
    statuses: ['offer'],
  },
  {
    id: 'rejected',
    label: 'Rejected',
    dotColor: '#e4e4e7',
    countColor: '#a1a1aa',
    countBg: '#f4f4f5',
    statuses: ['rejected', 'withdrawn'],
  },
]

interface LoadedData {
  applications: ApplicationCardData[]
  jobsById: Map<string, JobPosting>
}

type FetchState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: LoadedData }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; data: LoadedData }
  | { type: 'fetch_error'; message: string }
  | { type: 'update_status'; applicationId: string; newStatus: string }

function fetchReducer(state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', data: action.data }
    case 'fetch_error':
      return { status: 'error', message: action.message }
    case 'update_status': {
      if (state.status !== 'success') return state
      const updated = state.data.applications.map((app) =>
        app.id === action.applicationId ? { ...app, status: action.newStatus } : app,
      )
      return { ...state, data: { ...state.data, applications: updated } }
    }
  }
}

export default function ApplicationsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  // Kanban columns stagger in once data loads.
  const boardRef = useEntrance<HTMLDivElement>({
    stagger: MOTION.stagger,
    deps: [fetchState.status],
  })

  const loadData = useCallback((signal: AbortSignal) => {
    Promise.all([
      listApplications(undefined, signal),
      listJobs(undefined, signal),
    ])
      .then(([apps, jobsPage]) => {
        if (signal.aborted) return
        const jobsById = new Map<string, JobPosting>()
        for (const job of jobsPage.items) {
          jobsById.set(job.id, job)
        }
        dispatch({
          type: 'fetch_success',
          data: {
            // Cast: backend returns broader status union than pre-submission ApplicationStatus type
            applications: apps as unknown as ApplicationCardData[],
            jobsById,
          },
        })
      })
      .catch((err: unknown) => {
        if (signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load applications.'
        dispatch({ type: 'fetch_error', message })
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    loadData(controller.signal)
    return () => controller.abort()
  }, [loadData])

  function handleStatusChange(applicationId: string, newStatus: string) {
    dispatch({ type: 'update_status', applicationId, newStatus })

    updateApplicationStatus(applicationId, newStatus).catch((err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to update status.')
      const controller = new AbortController()
      dispatch({ type: 'fetch_start' })
      loadData(controller.signal)
    })
  }

  function handleDrop(columnId: string, applicationId: string) {
    const column = COLUMNS.find((c) => c.id === columnId)
    if (!column) return
    const targetStatus = column.statuses[0]
    if (!targetStatus) return
    handleStatusChange(applicationId, targetStatus)
  }

  const isLoading = fetchState.status === 'loading'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const applications = fetchState.status === 'success' ? fetchState.data.applications : []
  const jobsById = fetchState.status === 'success' ? fetchState.data.jobsById : new Map<string, JobPosting>()

  const totalCount = applications.length
  const responses = applications.filter((a) =>
    ['phone_screen', 'technical', 'onsite', 'offer'].includes(a.status),
  ).length

  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Applications</h1>
          <p className="text-xs text-muted-foreground">
            {isLoading
              ? 'Loading…'
              : loadError
                ? 'Error loading applications'
                : `${totalCount} total · ${responses} responses`}
          </p>
        </div>
      </header>

      <div className="p-6 overflow-x-auto">
        {isLoading && <div className="empty py-16">Loading applications…</div>}

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

        {!isLoading && !loadError && (
          <>
            <ProposedEvents
              onBoardRefresh={() => {
                const controller = new AbortController()
                dispatch({ type: 'fetch_start' })
                loadData(controller.signal)
              }}
            />
            <div ref={boardRef} className="grid grid-cols-5 gap-4 min-w-[1060px]">
              {COLUMNS.map((col) => {
                const colApps = applications.filter((a) => col.statuses.includes(a.status))
                return (
                  <div key={col.id} data-animate>
                    <KanbanColumn
                      id={col.id}
                      label={col.label}
                      dotColor={col.dotColor}
                      countColor={col.countColor}
                      countBg={col.countBg}
                      applications={colApps}
                      jobsById={jobsById}
                      onStatusChange={handleStatusChange}
                      onDrop={handleDrop}
                    />
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>
    </>
  )
}
