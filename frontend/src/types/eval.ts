export interface AssertionResult {
  kind: string
  passed: boolean
  score: number
  detail: string
}

export interface CaseResult {
  case_id: string
  passed: boolean
  score: number
  assertions: AssertionResult[]
}

export interface EvalRun {
  id: string
  suite_name: string
  prompt_version_id: string | null
  aggregate_scores: Record<string, number>
  results: CaseResult[]
  started_at: string
  completed_at: string | null
}
