export interface LlmCall {
  id: string
  prompt_version_id: string | null
  model: string
  input_tokens: number
  output_tokens: number
  latency_ms: number
  cost_usd: number
  error: string | null
  called_at: string
}

export interface LlmCallDetail extends LlmCall {
  inputs: Record<string, unknown>
  rendered_prompt: string
  response: string
  parsed_response: Record<string, unknown> | null
}

export interface CostByDay {
  day: string
  cost_usd: number
  calls: number
}

export interface CallTotals {
  total_cost: number
  total_calls: number
  avg_latency_ms: number
  error_rate: number
}

export interface CallCostResponse {
  by_day: CostByDay[]
  totals: CallTotals
}

export interface PromptVersion {
  id: string
  name: string
  version: number
  model: string
  temperature: number
  is_active: boolean
  created_at: string
}

export interface PromptDetail extends PromptVersion {
  template: string
  metadata: Record<string, unknown>
}
