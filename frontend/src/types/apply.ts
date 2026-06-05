export type ApplicationStatus =
  | 'queued'
  | 'filling'
  | 'review'
  | 'submitted'
  | 'failed'
  | 'blocked'

export type ApplyMode = 'manual' | 'auto'

export type FieldSource =
  | 'profile'
  | 'answer_bank'
  | 'cover_letter'
  | 'generated'
  | 'none'

export interface Application {
  id: string
  job_id: string
  status: ApplicationStatus
  apply_mode: ApplyMode
  apply_confidence: number
  blocked_reason: string | null
  submitted_at: string | null
  updated_at: string
}

export interface MappedField {
  field: {
    name: string
    label: string
    field_type: string
    options: string[]
    required: boolean
    is_knockout: boolean
  }
  value: string | null
  source: FieldSource
  confidence: number
}

export interface FieldMap {
  fields: MappedField[]
  overall_confidence: number
}

export interface ApplyQueueItem {
  application: Application
  field_map: FieldMap | null
  job: {
    company: string
    title: string
    source: string
  }
}

export type AutopilotMode = 'off' | 'selective' | 'full'

export interface AutopilotConfig {
  mode: AutopilotMode
  auto_submit_sources: string[]
  min_confidence: number
  min_fit: number
  daily_cap: number
}

export interface AnswerBankItem {
  id: string
  question: string
  answer: string
  approved: boolean
  reuse_count: number
}

export interface ProfileField {
  key: string
  value: string
  is_knockout: boolean
}
