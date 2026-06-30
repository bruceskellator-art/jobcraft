export interface ScrapeProfileConfig {
  query: string
  companies: string[]
  posted_within_days: number
  extract: boolean
}

export interface ScrapeResult {
  created: number
  runs: Array<{
    source: string
    total_listed: number
    total_fetched: number
    total_failed: number
    total_new: number
    error?: string | null
  }>
}
