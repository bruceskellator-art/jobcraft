const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS
const WEEK_MS = 7 * DAY_MS
const MONTH_MS = 30 * DAY_MS

/**
 * Returns a human-readable relative time string for a past ISO timestamp.
 * E.g. "just now", "3m ago", "2h ago", "5d ago", "3w ago", "2mo ago"
 */
export function relativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diff = now - then

  if (diff < MINUTE_MS) return 'just now'
  if (diff < HOUR_MS) return `${Math.floor(diff / MINUTE_MS)}m ago`
  if (diff < DAY_MS) return `${Math.floor(diff / HOUR_MS)}h ago`
  if (diff < WEEK_MS) return `${Math.floor(diff / DAY_MS)}d ago`
  if (diff < MONTH_MS) return `${Math.floor(diff / WEEK_MS)}w ago`
  return `${Math.floor(diff / MONTH_MS)}mo ago`
}
