export type ArtifactKind = 'resume' | 'cover_letter'
export type ArtifactFormat = 'markdown' | 'pdf' | 'json'

export interface ArtifactScores {
  fit: number
  groundedness: number
  ats_keywords: number
  quantified_impact: number
  clarity: number
}

export interface Artifact {
  id: string
  user_id: string
  job_id: string | null
  kind: ArtifactKind
  format: ArtifactFormat
  content: string
  is_baseline: boolean
  scores: ArtifactScores | null
  prompt_version_id: string | null
  template_id: string | null
  created_at: string
}

export interface ResumeTemplate {
  id: string
  name: string
  description: string
  thumbnail_url: string
}

export interface StyleConfig {
  tone: 'professional' | 'conversational' | 'concise'
  length: 'brief' | 'standard' | 'detailed'
  emphasis: string[]
}
