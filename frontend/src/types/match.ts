export type GapSeverity = 'low' | 'mid' | 'high'

export interface Gap {
  skill: string
  severity: GapSeverity
  rationale: string
}

export interface MatchRead {
  overall_score: number
  dimension_scores: Record<string, number>
  gaps: Gap[]
  rationale: string
  computed_at: string
}
