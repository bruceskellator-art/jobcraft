export type ExperienceKind = 'work' | 'project' | 'education' | 'skill' | 'achievement'

export interface ExperienceItem {
  id: string
  user_id: string
  kind: ExperienceKind
  title?: string
  organization?: string
  start_date?: string
  end_date?: string
  content: string
  tags: string[]
  created_at: string
  updated_at: string
}

export interface CreateExperiencePayload {
  kind: ExperienceKind
  title?: string
  organization?: string
  start_date?: string
  end_date?: string
  content: string
  tags: string[]
}

export type UpdateExperiencePayload = Partial<CreateExperiencePayload>
