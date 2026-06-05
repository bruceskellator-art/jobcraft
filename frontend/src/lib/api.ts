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

// --- Artifacts ---

import type { Artifact, StyleConfig, ArtifactKind } from '@/types/artifact'

export interface GenerateArtifactPayload {
  kind: ArtifactKind
  style: StyleConfig
}

export async function generateArtifact(
  jobId: string,
  payload: GenerateArtifactPayload,
  signal?: AbortSignal,
): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  return handleResponse<Artifact>(res)
}

export async function listJobArtifacts(jobId: string, signal?: AbortSignal): Promise<Artifact[]> {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/artifacts`, { signal })
  return handleResponse<Artifact[]>(res)
}

export async function listArtifacts(signal?: AbortSignal): Promise<Artifact[]> {
  const res = await fetch(`${BASE}/api/artifacts`, { signal })
  return handleResponse<Artifact[]>(res)
}

export async function getArtifact(id: string, signal?: AbortSignal): Promise<Artifact> {
  const res = await fetch(`${BASE}/api/artifacts/${id}`, { signal })
  return handleResponse<Artifact>(res)
}

export async function uploadBaseline(file: File, signal?: AbortSignal): Promise<Artifact> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/artifacts/baseline`, {
    method: 'POST',
    body: form,
    signal,
  })
  return handleResponse<Artifact>(res)
}

// --- Apply Queue ---

import type {
  ApplyQueueItem,
  Application,
  AutopilotConfig,
  AnswerBankItem,
  ProfileField,
} from '@/types/apply'

export async function getApplyQueue(signal?: AbortSignal): Promise<ApplyQueueItem[]> {
  const res = await fetch(`${BASE}/api/apply/queue`, { signal })
  return handleResponse<ApplyQueueItem[]>(res)
}

export async function listApplications(
  status?: string,
  signal?: AbortSignal,
): Promise<Application[]> {
  const url = new URL(`${BASE}/api/applications`)
  if (status) url.searchParams.set('status', status)
  const res = await fetch(url.toString(), { signal })
  return handleResponse<Application[]>(res)
}

export async function approveApplication(id: string): Promise<Application> {
  const res = await fetch(`${BASE}/api/applications/${id}/approve`, { method: 'POST' })
  return handleResponse<Application>(res)
}

export interface ProcessApplicationResult {
  id: string
  application_id: string
  status: string
  dry_run: boolean
  created_at: string
}

export async function processApplication(
  id: string,
  dryRun: boolean,
): Promise<ProcessApplicationResult> {
  const res = await fetch(`${BASE}/api/applications/${id}/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dry_run: dryRun }),
  })
  return handleResponse<ProcessApplicationResult>(res)
}

export async function updateApplicationStatus(
  id: string,
  status: string,
): Promise<Application> {
  const res = await fetch(`${BASE}/api/applications/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  return handleResponse<Application>(res)
}

// --- Profile Fields ---

export async function getProfileFields(signal?: AbortSignal): Promise<ProfileField[]> {
  const res = await fetch(`${BASE}/api/profile/fields`, { signal })
  return handleResponse<ProfileField[]>(res)
}

export async function putProfileField(
  key: string,
  value: string,
  is_knockout: boolean,
): Promise<ProfileField> {
  const res = await fetch(`${BASE}/api/profile/fields`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value, is_knockout }),
  })
  return handleResponse<ProfileField>(res)
}

export async function deleteProfileField(key: string): Promise<void> {
  const res = await fetch(`${BASE}/api/profile/fields/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  })
  await handleResponse<void>(res)
}

// --- Autopilot ---

export async function getAutopilot(signal?: AbortSignal): Promise<AutopilotConfig> {
  const res = await fetch(`${BASE}/api/profile/autopilot`, { signal })
  return handleResponse<AutopilotConfig>(res)
}

export async function putAutopilot(config: AutopilotConfig): Promise<AutopilotConfig> {
  const res = await fetch(`${BASE}/api/profile/autopilot`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  return handleResponse<AutopilotConfig>(res)
}

// --- Answer Bank ---

export async function listAnswers(signal?: AbortSignal): Promise<AnswerBankItem[]> {
  const res = await fetch(`${BASE}/api/answers`, { signal })
  return handleResponse<AnswerBankItem[]>(res)
}

export async function createAnswer(
  question: string,
  answer: string,
): Promise<AnswerBankItem> {
  const res = await fetch(`${BASE}/api/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, answer }),
  })
  return handleResponse<AnswerBankItem>(res)
}

export async function approveAnswer(
  id: string,
  approved: boolean,
): Promise<AnswerBankItem> {
  const res = await fetch(`${BASE}/api/answers/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved }),
  })
  return handleResponse<AnswerBankItem>(res)
}

// --- Evals ---

import type { EvalRun } from '@/types/eval'

export async function listEvalRuns(signal?: AbortSignal): Promise<EvalRun[]> {
  const res = await fetch(`${BASE}/api/admin/evals`, { signal })
  return handleResponse<EvalRun[]>(res)
}

export async function getEvalRun(id: string, signal?: AbortSignal): Promise<EvalRun> {
  const res = await fetch(`${BASE}/api/admin/evals/${id}`, { signal })
  return handleResponse<EvalRun>(res)
}

export interface RunEvalSuitePayload {
  suite_name: string
  prompt_version?: string
}

export async function runEvalSuite(
  suiteName: string,
  promptVersion?: string,
  signal?: AbortSignal,
): Promise<EvalRun> {
  const payload: RunEvalSuitePayload = {
    suite_name: suiteName,
    ...(promptVersion !== undefined ? { prompt_version: promptVersion } : {}),
  }
  const res = await fetch(`${BASE}/api/admin/evals/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  return handleResponse<EvalRun>(res)
}
