interface DimensionBarProps {
  label: string
  score: number
}

function barColorClass(score: number): string {
  if (score >= 0.75) return 'bg-emerald-500'
  if (score >= 0.5) return 'bg-amber-400'
  return 'bg-rose-400'
}

function scoreColorClass(score: number): string {
  if (score >= 0.75) return 'text-emerald-600'
  if (score >= 0.5) return 'text-amber-600'
  return 'text-rose-600'
}

function formatLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

export function DimensionBar({ label, score }: DimensionBarProps) {
  const pct = Math.round(score * 100)

  return (
    <div>
      <div className="flex justify-between mb-1.5">
        <span className="text-muted-foreground text-sm">{formatLabel(label)}</span>
        <span className={`num font-semibold text-sm ${scoreColorClass(score)}`}>
          {score.toFixed(2)}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-muted">
        <div
          data-bar
          className={`h-full rounded-full ${barColorClass(score)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
