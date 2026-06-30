'use client'

import { useState, useEffect, useReducer, useCallback, useRef } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { toast } from 'sonner'
import { entrance } from '@/lib/motion'
import { Toaster } from '@/components/ui/sonner'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { JobPosting } from '@/types/job'
import { listJobs, runMatches, type ListJobsParams } from '@/lib/api'
import { JobRow } from '@/components/jobs/JobRow'
import {
  JobsToolbar,
  type ScoredFilter,
  type SortOption,
} from '@/components/jobs/JobsToolbar'

const DEBOUNCE_MS = 300
const PAGE_SIZE = 50

type FetchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; jobs: JobPosting[]; total: number }

type FetchAction =
  | { type: 'fetch_start' }
  | { type: 'fetch_success'; jobs: JobPosting[]; total: number }
  | { type: 'fetch_error'; message: string }

function fetchReducer(_state: FetchState, action: FetchAction): FetchState {
  switch (action.type) {
    case 'fetch_start':
      return { status: 'loading' }
    case 'fetch_success':
      return { status: 'success', jobs: action.jobs, total: action.total }
    case 'fetch_error':
      return { status: 'error', message: action.message }
  }
}

interface JobFilters {
  search: string
  source: string
  scored: ScoredFilter
  sort: SortOption
  minFit: string
}

function scoredToParam(scored: ScoredFilter): boolean | undefined {
  if (scored === 'scored') return true
  if (scored === 'unscored') return false
  return undefined
}

export default function JobsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [source, setSource] = useState('all')
  const [scored, setScored] = useState<ScoredFilter>('all')
  const [sort, setSort] = useState<SortOption>('recent')
  const [minFit, setMinFit] = useState('any')
  const [offset, setOffset] = useState(0)
  // Bumped to force the main fetch effect to re-run (e.g. after scoring new
  // jobs), so all fetching stays in one place with one abort-managed controller.
  const [refetchNonce, setRefetchNonce] = useState(0)

  const [isRunningMatches, setIsRunningMatches] = useState(false)
  const runMatchesAbortRef = useRef<AbortController | null>(null)

  // Debounce the search input, resetting to the first page when it settles.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput)
      setOffset(0)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  // Filter setters that also reset pagination to the first page in the SAME
  // render, so changing a filter triggers exactly one fetch with offset 0
  // (no stale-offset fetch followed by a corrective second fetch).
  const handleSourceChange = useCallback((value: string) => {
    setSource(value)
    setOffset(0)
  }, [])
  const handleScoredChange = useCallback((value: ScoredFilter) => {
    setScored(value)
    setOffset(0)
  }, [])
  const handleSortChange = useCallback((value: SortOption) => {
    setSort(value)
    setOffset(0)
  }, [])
  const handleMinFitChange = useCallback((value: string) => {
    setMinFit(value)
    setOffset(0)
  }, [])

  const fetchJobs = useCallback(
    (filters: JobFilters, pageOffset: number, signal: AbortSignal) => {
      const params: ListJobsParams = {
        sort: filters.sort,
        limit: PAGE_SIZE,
        offset: pageOffset,
        ...(filters.source !== 'all' ? { source: filters.source } : {}),
        ...(filters.search.trim() ? { q: filters.search.trim() } : {}),
        ...(scoredToParam(filters.scored) !== undefined
          ? { scored: scoredToParam(filters.scored) }
          : {}),
        ...(filters.minFit !== 'any' ? { min_fit: Number(filters.minFit) } : {}),
      }

      listJobs(params, signal)
        .then(data => {
          if (!signal.aborted) {
            dispatch({ type: 'fetch_success', jobs: data.items, total: data.total })
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

  const currentFilters: JobFilters = {
    search: debouncedSearch,
    source,
    scored,
    sort,
    minFit,
  }

  // Fetch when filters or page change.
  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    fetchJobs(currentFilters, offset, controller.signal)
    return () => controller.abort()
    // currentFilters is derived from the primitive deps listed below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, source, scored, sort, minFit, offset, refetchNonce, fetchJobs])

  function handleRetry() {
    // Re-run the main fetch effect; its controller handles abort on cleanup.
    setRefetchNonce(n => n + 1)
  }

  async function handleScoreNewJobs() {
    if (isRunningMatches) return
    runMatchesAbortRef.current?.abort()
    const controller = new AbortController()
    runMatchesAbortRef.current = controller
    setIsRunningMatches(true)
    try {
      const result = await runMatches({ only_unscored: true }, controller.signal)
      if (result.total === 0) {
        toast.success('All jobs already scored ✓')
      } else {
        const failedSuffix = result.failed > 0 ? `, ${result.failed} failed` : ''
        toast.success(
          `Scored ${result.matched} new job${result.matched !== 1 ? 's' : ''}${failedSuffix}`,
        )
      }
      // Refetch to surface updated match scores. Routed through the main fetch
      // effect (via the nonce) so the request is abort-managed and we never
      // setState after unmount.
      setRefetchNonce(n => n + 1)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      toast.error(err instanceof Error ? err.message : 'Failed to score jobs.')
    } finally {
      setIsRunningMatches(false)
    }
  }

  const isLoading = fetchState.status === 'loading' || fetchState.status === 'idle'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const jobs = fetchState.status === 'success' ? fetchState.jobs : []
  const total = fetchState.status === 'success' ? fetchState.total : 0

  const tableRef = useRef<HTMLDivElement>(null)
  // Subtle staggered fade-in of the real rows once results land. Keyed on the
  // result set so it replays per page / filter change. Opacity + tiny slide
  // only — no height changes, so it doesn't introduce layout shift.
  const rowsSignature = jobs.map(j => j.id).join(',')
  useGSAP(
    () => {
      if (!tableRef.current) return
      // JobRow renders each row as `<tr class="data-row">`, so this matches the
      // real rows; scoped to tableRef so it never reaches other tables.
      const rows = gsap.utils.toArray<HTMLElement>('tbody tr.data-row', tableRef.current)
      if (rows.length === 0) return
      entrance(rows, { stagger: 0.03, y: 6 })
    },
    { scope: tableRef, dependencies: [rowsSignature], revertOnUpdate: true },
  )

  const rangeStart = total === 0 ? 0 : offset + 1
  const rangeEnd = offset + jobs.length
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

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
                : `${total} job${total !== 1 ? 's' : ''}`}
          </p>
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  className="btn btn-ghost cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => void handleScoreNewJobs()}
                  disabled={isRunningMatches}
                >
                  {isRunningMatches ? 'Scoring…' : 'Score new jobs'}
                </button>
              }
            />
            <TooltipContent>Score jobs that haven&apos;t been matched yet</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </header>

      <JobsToolbar
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        source={source}
        onSourceChange={handleSourceChange}
        scored={scored}
        onScoredChange={handleScoredChange}
        sort={sort}
        onSortChange={handleSortChange}
        minFit={minFit}
        onMinFitChange={handleMinFitChange}
      />

      <div className="p-6">
        {isLoading && <JobsTableSkeleton />}

        {!isLoading && loadError && (
          <div className="bg-destructive/10 border border-destructive/30 rounded-xl px-4 py-3 text-sm text-destructive">
            {loadError}
            <button
              onClick={handleRetry}
              className="ml-2 underline cursor-pointer hover:opacity-80"
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
          <div ref={tableRef} className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <JobsTableHead />
              <tbody className="divide-y divide-border">
                {jobs.map(job => (
                  <JobRow key={job.id} job={job} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && !loadError && total > 0 && (
          <div className="flex items-center justify-between mt-3">
            <p className="text-xs text-muted-foreground">
              {rangeStart}–{rangeEnd} of {total}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))}
                disabled={!hasPrev}
                className="btn btn-ghost text-xs cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span aria-hidden="true">←</span> Prev
              </button>
              <button
                onClick={() => setOffset(o => o + PAGE_SIZE)}
                disabled={!hasNext}
                className="btn btn-ghost text-xs cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next <span aria-hidden="true">→</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function JobsTableHead() {
  return (
    <thead className="bg-muted/80 text-muted-foreground text-xs border-b border-border">
      <tr className="text-left">
        <th className="px-4 py-2.5 font-medium w-16">Fit</th>
        <th className="px-4 py-2.5 font-medium">Role &amp; Skills</th>
        <th className="px-4 py-2.5 font-medium">Company</th>
        <th className="px-4 py-2.5 font-medium">Location</th>
        <th className="px-4 py-2.5 font-medium w-16">Age</th>
        <th className="px-4 py-2.5 font-medium w-32">Source</th>
        <th className="px-4 py-2.5 font-medium text-right w-24 pl-6">Action</th>
      </tr>
    </thead>
  )
}

const SKELETON_ROWS = 8

// A shimmer skeleton matching the jobs table column layout. Keeps the same
// structure as the real table to reduce layout shift while loading.
function JobsTableSkeleton() {
  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <JobsTableHead />
        <tbody className="divide-y divide-border">
          {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
            <tr key={i} className="animate-pulse">
              <td className="px-4 py-3">
                <div className="h-5 w-10 rounded-full bg-muted" />
              </td>
              <td className="px-4 py-3">
                <div className="h-4 w-48 rounded bg-muted" />
                <div className="mt-2 flex gap-1.5">
                  <div className="h-4 w-12 rounded bg-muted" />
                  <div className="h-4 w-16 rounded bg-muted" />
                  <div className="h-4 w-10 rounded bg-muted" />
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded bg-muted" />
                  <div className="h-4 w-24 rounded bg-muted" />
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="h-3 w-20 rounded bg-muted" />
              </td>
              <td className="px-4 py-3">
                <div className="h-3 w-8 rounded bg-muted" />
              </td>
              <td className="px-4 py-3">
                <div className="h-5 w-20 rounded-full bg-muted" />
              </td>
              <td className="px-4 py-3 pl-6">
                <div className="ml-auto h-7 w-14 rounded-lg bg-muted" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
