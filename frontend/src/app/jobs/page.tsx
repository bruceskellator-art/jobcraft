'use client'

import { useState, useEffect, useReducer, useCallback } from 'react'
import type { JobPosting, JobSource } from '@/types/job'
import { listJobs } from '@/lib/api'
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

  const isLoading = fetchState.status === 'loading' || fetchState.status === 'idle'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const jobs = fetchState.status === 'success' ? fetchState.jobs : []

  return (
    <>
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Jobs</h1>
          <p className="text-xs text-zinc-400">
            {isLoading
              ? 'Loading…'
              : loadError
                ? 'Error loading jobs'
                : `${jobs.length} job${jobs.length !== 1 ? 's' : ''} · fit scoring coming in Phase 3`}
          </p>
        </div>
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
          <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50/80 text-zinc-500 text-xs border-b border-zinc-100">
                <tr className="text-left">
                  <th className="px-4 py-2.5 font-medium w-16">Fit</th>
                  <th className="px-4 py-2.5 font-medium">Role &amp; Skills</th>
                  <th className="px-4 py-2.5 font-medium">Company</th>
                  <th className="px-4 py-2.5 font-medium">Location</th>
                  <th className="px-4 py-2.5 font-medium w-16">Age</th>
                  <th className="px-4 py-2.5 font-medium text-right w-32">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {jobs.map(job => (
                  <JobRow key={job.id} job={job} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && !loadError && jobs.length > 0 && (
          <p className="text-xs text-zinc-400 mt-3">
            Showing {jobs.length} job{jobs.length !== 1 ? 's' : ''} · fit scoring available in Phase 3
          </p>
        )}
      </div>
    </>
  )
}
