'use client'

import { useState, useEffect, useReducer, useCallback, useRef } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import type { JobPosting, JobSource } from '@/types/job'
import { listJobs, runMatches } from '@/lib/api'
import { JobRow } from '@/components/jobs/JobRow'
import { JobsToolbar } from '@/components/jobs/JobsToolbar'

const DEBOUNCE_MS = 300

type FetchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; jobs: JobPosting[] }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; jobs: JobPosting[] }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', jobs: action.jobs }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

export default function JobsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [activeSource, setActiveSource] = useState<JobSource>('all')
  const [isRunningMatches, setIsRunningMatches] = useState(false)
  const runMatchesAbortRef = useRef<AbortController | null>(null)

  // Debounce the search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  const fetchJobs = useCallback(
    (search: string, source: JobSource, signal: AbortSignal) => {
      const params = {
        ...(source !== 'all' ? { source } : {}),
        ...(search.trim() ? { q: search.trim() } : {}),
      }

      listJobs(params, signal)
        .then(data => {
          if (!signal.aborted) {
            dispatch({ type: 'fetch_success', jobs: data })
          }
        })
        .catch((err: unknown) => {
          if (!signal.aborted) {
            dispatch({
              type: 'fetch_error',
              message: err instanceof Error ? err.message : 'Failed to load jobs.',
            })
          }
        })
    },
    [],
  )

  // Fetch when filters change — dispatch fetch_start at start of effect
  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    fetchJobs(debouncedSearch, activeSource, controller.signal)
    return () => controller.abort()
  }, [debouncedSearch, activeSource, fetchJobs])

  function handleRetry() {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    fetchJobs(debouncedSearch, activeSource, controller.signal)
  }

  async function handleRunMatches() {
    if (isRunningMatches) return
    runMatchesAbortRef.current?.abort()
    const controller = new AbortController()
    runMatchesAbortRef.current = controller
    setIsRunningMatches(true)
    try {
      const result = await runMatches(undefined, controller.signal)
      toast.success(`Scored ${result.matched} job${result.matched !== 1 ? 's' : ''}.`)
      // Refetch to get updated match scores
      const refetchController = new AbortController()
      dispatch({ type: 'fetch_start' })
      fetchJobs(debouncedSearch, activeSource, refetchController.signal)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      toast.error(err instanceof Error ? err.message : 'Failed to run matches.')
    } finally {
      setIsRunningMatches(false)
    }
  }

  const isLoading = fetchState.status === 'loading' || fetchState.status === 'idle'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const jobs = fetchState.status === 'success' ? fetchState.jobs : []

  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Jobs</h1>
          <p className="text-xs text-muted-foreground">
            {isLoading
              ? 'Loading…'
              : loadError
                ? 'Error loading jobs'
                : `${jobs.length} job${jobs.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <button
          className="btn btn-ghost"
          onClick={() => void handleRunMatches()}
          disabled={isRunningMatches}
        >
          {isRunningMatches ? 'Scoring…' : 'Run matches'}
        </button>
      </header>

      <JobsToolbar
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        activeSource={activeSource}
        onSourceChange={setActiveSource}
      />

      <div className="p-6">
        {isLoading && (
          <div className="empty py-16">Loading jobs…</div>
        )}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
            <button
              onClick={handleRetry}
              className="ml-2 underline text-red-600 hover:text-red-800"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !loadError && jobs.length === 0 && (
          <div className="empty py-16">
            No jobs found. Try adjusting your search or filters.
          </div>
        )}

        {!isLoading && !loadError && jobs.length > 0 && (
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-muted-foreground text-xs border-b border-border">
                <tr className="text-left">
                  <th className="px-4 py-2.5 font-medium w-16">Fit</th>
                  <th className="px-4 py-2.5 font-medium">Role &amp; Skills</th>
                  <th className="px-4 py-2.5 font-medium">Company</th>
                  <th className="px-4 py-2.5 font-medium">Location</th>
                  <th className="px-4 py-2.5 font-medium w-16">Age</th>
                  <th className="px-4 py-2.5 font-medium text-right w-32">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {jobs.map(job => (
                  <JobRow key={job.id} job={job} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && !loadError && jobs.length > 0 && (
          <p className="text-xs text-muted-foreground mt-3">
            Showing {jobs.length} job{jobs.length !== 1 ? 's' : ''}
          </p>
        )}
      </div>
    </>
  )
}
