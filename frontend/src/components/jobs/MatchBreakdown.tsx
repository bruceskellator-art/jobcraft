import type { MatchRead, GapSeverity } from '@/types/match'
import { DimensionBar } from './DimensionBar'

interface MatchBreakdownProps {
  match: MatchRead
}

function gapTagStyle(severity: GapSeverity): React.CSSProperties {
  switch (severity) {
    case 'high':
      return { background: '#fff1f2', color: '#be123c', borderColor: '#fecdd3' }
    case 'mid':
      return { background: '#fff7ed', color: '#c2410c', borderColor: '#fed7aa' }
    case 'low':
      return { background: '#f0fdf4', color: '#15803d', borderColor: '#bbf7d0' }
  }
}

function overallChipClass(score: number): string {
  if (score >= 0.75) return 'chip chip-high'
  if (score >= 0.5) return 'chip chip-mid'
  return 'chip chip-low'
}

export function MatchBreakdown({ match }: MatchBreakdownProps) {
  const dimensions = Object.entries(match.dimension_scores)

  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">Match breakdown</h2>
        <span className={overallChipClass(match.overall_score)}>
          {Math.round(match.overall_score * 100)}%
        </span>
      </div>

      {dimensions.length > 0 && (
        <div className="p-4 grid grid-cols-2 gap-x-8 gap-y-4">
          {dimensions.map(([key, score]) => (
            <DimensionBar key={key} label={key} score={score} />
          ))}
        </div>
      )}

      {match.gaps.length > 0 && (
        <div className="px-4 pb-4">
          <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
            Gaps to address
          </div>
          <div className="flex flex-wrap gap-1.5">
            {match.gaps.map(gap => (
              <span
                key={gap.skill}
                className="skill-tag"
                style={gapTagStyle(gap.severity)}
                title={gap.rationale}
              >
                {gap.skill}
                <span className="text-xs opacity-60 ml-1">{gap.severity}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {match.rationale && (
        <div className="px-4 pb-4">
          <p className="text-xs text-muted-foreground leading-relaxed">{match.rationale}</p>
        </div>
      )}
    </section>
  )
}
