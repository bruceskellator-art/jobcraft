import type { MatchRead } from '@/types/match'

export interface ExtractedJobView {
  company: string
  title: string
  seniority?: string
  location?: string
  remote_policy?: string
  salary_min_usd?: number
  salary_max_usd?: number
  required_skills: string[]
  preferred_skills: string[]
  summary: string
}

export interface JobPosting {
  id: string
  source: string
  source_url: string
  source_id?: string
  company: string
  title: string
  location?: string
  remote_policy?: string
  scraped_at: string
  extracted: ExtractedJobView | null
  match: MatchRead | null
}

export type JobSource = 'greenhouse' | 'lever' | 'all'
