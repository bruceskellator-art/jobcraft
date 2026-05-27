import type { ExperienceItem, CreateExperiencePayload, UpdateExperiencePayload } from '@/types/experience'

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json() as { detail?: string; message?: string }
      message = body.detail ?? body.message ?? message
    } catch {
      // use statusText as fallback
    }
    throw new ApiError(res.status, message)
  }
  // 204 No Content (or any empty body) — return undefined for void callers
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T
  }
  return res.json() as Promise<T>
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function listExperience(signal?: AbortSignal): Promise<ExperienceItem[]> {
  const res = await fetch(`${BASE}/api/experience`, { signal })
  return handleResponse<ExperienceItem[]>(res)
}

export async function createExperience(payload: CreateExperiencePayload): Promise<ExperienceItem> {
  const res = await fetch(`${BASE}/api/experience`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return handleResponse<ExperienceItem>(res)
}

export async function updateExperience(id: string, payload: UpdateExperiencePayload): Promise<ExperienceItem> {
  const res = await fetch(`${BASE}/api/experience/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return handleResponse<ExperienceItem>(res)
}

export async function deleteExperience(id: string): Promise<void> {
  const res = await fetch(`${BASE}/api/experience/${id}`, { method: 'DELETE' })
  await handleResponse<void>(res)
}

export interface ImportResult {
  created: ExperienceItem[]
}

export async function importResume(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/experience/import`, {
    method: 'POST',
    body: form,
  })
  return handleResponse<ImportResult>(res)
}

// --- Jobs ---

import type { JobPosting } from '@/types/job'

export interface ListJobsParams {
  source?: string
  q?: string
}

export async function listJobs(
  params?: ListJobsParams,
  signal?: AbortSignal,
): Promise<JobPosting[]> {
  const url = new URL(`${BASE}/api/jobs`)
  if (params?.source) url.searchParams.set('source', params.source)
  if (params?.q) url.searchParams.set('q', params.q)
  const res = await fetch(url.toString(), { signal })
  return handleResponse<JobPosting[]>(res)
}

export async function getJob(id: string, signal?: AbortSignal): Promise<JobPosting> {
  const res = await fetch(`${BASE}/api/jobs/${id}`, { signal })
  return handleResponse<JobPosting>(res)
}

import type { MatchRead } from '@/types/match'

export async function getJobMatch(id: string, signal?: AbortSignal): Promise<MatchRead> {
  const res = await fetch(`${BASE}/api/jobs/${id}/match`, { signal })
  return handleResponse<MatchRead>(res)
}

export interface RunMatchesResult {
  matched: number
}

export async function runMatches(limit?: number, signal?: AbortSignal): Promise<RunMatchesResult> {
  const res = await fetch(`${BASE}/api/match/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...(limit !== undefined ? { limit } : {}) }),
    signal,
  })
  return handleResponse<RunMatchesResult>(res)
}
