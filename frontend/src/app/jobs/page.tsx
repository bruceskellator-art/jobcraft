'use client'

import { useState, useEffect, useReducer, useCallback, useRef } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { toast } from 'sonner'
import { ScanSearchIcon } from 'lucide-react'
import { entrance, MOTION } from '@/lib/motion'
import { Toaster } from '@/components/ui/sonner'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetBody,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import type { JobPosting } from '@/types/job'
import type { ScrapeProfileConfig } from '@/types/settings'
import {
  listJobs,
  runMatches,
  getScrapeProfile,
  putScrapeProfile,
  enqueueScrape,
  type ListJobsParams,
} from '@/lib/api'
import { JobRow } from '@/components/jobs/JobRow'
import {
  JobsToolbar,
  type ScoredFilter,
  type SortOption,
  type RecencyOption,
} from '@/components/jobs/JobsToolbar'
import { ScrapeProfileForm } from '@/components/settings/ScrapeProfileForm'

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
  location: string
  recency: RecencyOption
}

function scoredToParam(scored: ScoredFilter): boolean | undefined {
  if (scored === 'scored') return true
  if (scored === 'unscored') return false
  return undefined
}

function recencyToDays(recency: RecencyOption): number | undefined {
  if (recency === 'any') return undefined
  return Number(recency)
}

export default function JobsPage() {
  const [fetchState, dispatch] = useReducer(fetchReducer, { status: 'loading' })

  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [source, setSource] = useState('all')
  const [scored, setScored] = useState<ScoredFilter>('all')
  const [sort, setSort] = useState<SortOption>('recent')
  const [minFit, setMinFit] = useState('any')
  const [locationInput, setLocationInput] = useState('')
  const [debouncedLocation, setDebouncedLocation] = useState('')
  const [recency, setRecency] = useState<RecencyOption>('any')
  const [offset, setOffset] = useState(0)
  // Bumped to force the main fetch effect to re-run (e.g. after scoring new
  // jobs), so all fetching stays in one place with one abort-managed controller.
  const [refetchNonce, setRefetchNonce] = useState(0)

  // Sheet / scrape panel state
  const [sheetOpen, setSheetOpen] = useState(false)
  const [scrapeProfile, setScrapeProfile] = useState<ScrapeProfileConfig | null>(null)
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [isEnqueueing, setIsEnqueueing] = useState(false)
  const [isScraping, setIsScraping] = useState(false)

  const [isRunningMatches, setIsRunningMatches] = useState(false)
  const runMatchesAbortRef = useRef<AbortController | null>(null)

  // Load scrape profile once on mount so the Sheet form is pre-populated.
  useEffect(() => {
    const controller = new AbortController()
    getScrapeProfile(controller.signal)
      .then(setScrapeProfile)
      .catch(() => {
        // Non-critical — the form still renders with empty defaults if this fails.
      })
    return () => controller.abort()
  }, [])

  // Debounce the search input, resetting to the first page when it settles.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput)
      setOffset(0)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [searchInput])

  // Debounce the location input, resetting pagination on settle.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedLocation(locationInput)
      setOffset(0)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [locationInput])

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
  const handleRecencyChange = useCallback((value: RecencyOption) => {
    setRecency(value)
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
        ...(filters.location.trim() ? { location: filters.location.trim() } : {}),
        ...(recencyToDays(filters.recency) !== undefined
          ? { posted_within_days: recencyToDays(filters.recency) }
          : {}),
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
    location: debouncedLocation,
    recency,
  }

  // Fetch when filters or page change.
  useEffect(() => {
    const controller = new AbortController()
    dispatch({ type: 'fetch_start' })
    fetchJobs(currentFilters, offset, controller.signal)
    return () => controller.abort()
    // currentFilters is derived from the primitive deps listed below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, source, scored, sort, minFit, debouncedLocation, recency, offset, refetchNonce, fetchJobs])

  function handleRetry() {
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
      setRefetchNonce(n => n + 1)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      toast.error(err instanceof Error ? err.message : 'Failed to score jobs.')
    } finally {
      setIsRunningMatches(false)
    }
  }

  async function handleSaveProfile(config: ScrapeProfileConfig) {
    if (isSavingProfile) return
    setIsSavingProfile(true)
    try {
      const updated = await putScrapeProfile(config)
      setScrapeProfile(updated)
      toast.success('Scrape profile saved.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to save scrape profile.')
      throw err
    } finally {
      setIsSavingProfile(false)
    }
  }

  async function handleRunScrape(config: ScrapeProfileConfig) {
    if (isEnqueueing) return
    setIsEnqueueing(true)
    try {
      await enqueueScrape(config)
      toast.success('Scrape queued — track it on Activity')
      setSheetOpen(false)
      // Surface a subtle hint that scraping is underway, then refresh after a
      // short delay to surface any fast results.
      setIsScraping(true)
      setTimeout(() => {
        setIsScraping(false)
        setRefetchNonce(n => n + 1)
      }, 4000)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Scrape failed.')
      throw err
    } finally {
      setIsEnqueueing(false)
    }
  }

  const isLoading = fetchState.status === 'loading' || fetchState.status === 'idle'
  const loadError = fetchState.status === 'error' ? fetchState.message : null
  const jobs = fetchState.status === 'success' ? fetchState.jobs : []
  const total = fetchState.status === 'success' ? fetchState.total : 0

  const tableRef = useRef<HTMLDivElement>(null)
  // Snappy staggered fade-in keyed on result set — replays only when the job
  // IDs change (filter/page/refetch), NOT on unrelated state changes such as
  // the Sheet open/close toggle. Using a ref-tracked prev signature avoids
  // revertOnUpdate replaying (and flashing) on every re-render.
  const rowsSignature = jobs.map(j => j.id).join(',')
  const prevSignatureRef = useRef('')
  useGSAP(
    () => {
      if (!tableRef.current) return
      if (rowsSignature === prevSignatureRef.current) return
      prevSignatureRef.current = rowsSignature
      const rows = gsap.utils.toArray<HTMLElement>('tbody tr.data-row', tableRef.current)
      if (rows.length === 0) return
      entrance(rows, { stagger: MOTION.staggerTight, y: 6, duration: 0.3 })
    },
    { scope: tableRef, dependencies: [rowsSignature] },
  )

  const rangeStart = total === 0 ? 0 : offset + 1
  const rangeEnd = offset + jobs.length
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  // Default profile to show in the sheet when the API hasn't returned yet.
  const profileForSheet: ScrapeProfileConfig = scrapeProfile ?? {
    query: '',
    companies: [],
    location: '',
    posted_within_days: 7,
    extract: false,
  }

  return (
    <>
      <Toaster />

      {/* Scrape-jobs Sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>Scrape jobs</SheetTitle>
            <SheetDescription>
              Tweak your profile and run a scrape. Results appear on the Activity page.
            </SheetDescription>
          </SheetHeader>
          <SheetBody>
            <ScrapeProfileForm
              initial={profileForSheet}
              onSave={handleSaveProfile}
              onRun={handleRunScrape}
              isSaving={isSavingProfile}
              isRunning={isEnqueueing}
            />
          </SheetBody>
        </SheetContent>
      </Sheet>

      <header className="h-14 bg-card border-b border-border flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Jobs</h1>
          <p className="text-xs text-muted-foreground">
            {isLoading
              ? 'Loading…'
              : loadError
                ? 'Error loading jobs'
                : isScraping
                  ? `${total} job${total !== 1 ? 's' : ''} · scraping…`
                  : `${total} job${total !== 1 ? 's' : ''}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="default"
            size="sm"
            className="cursor-pointer gap-1.5"
            onClick={() => setSheetOpen(true)}
          >
            <ScanSearchIcon size={14} />
            Scrape jobs
          </Button>

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
        </div>
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
        locationInput={locationInput}
        onLocationInputChange={setLocationInput}
        recency={recency}
        onRecencyChange={handleRecencyChange}
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
          <EmptyState onOpenSheet={() => setSheetOpen(true)} />
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

interface EmptyStateProps {
  onOpenSheet: () => void
}

function EmptyState({ onOpenSheet }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <div className="rounded-full bg-muted p-4">
        <ScanSearchIcon size={28} className="text-muted-foreground" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">No jobs yet</p>
        <p className="text-xs text-muted-foreground max-w-xs">
          Scrape your first batch to start discovering roles that match your profile.
        </p>
      </div>
      <Button
        variant="default"
        size="sm"
        className="cursor-pointer gap-1.5 mt-1"
        onClick={onOpenSheet}
      >
        <ScanSearchIcon size={14} />
        Scrape your first batch
      </Button>
    </div>
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
