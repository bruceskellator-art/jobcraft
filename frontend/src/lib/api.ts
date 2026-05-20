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
  return res.json() as Promise<T>
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function listExperience(): Promise<ExperienceItem[]> {
  const res = await fetch(`${BASE}/api/experience`)
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
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText)
  }
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
