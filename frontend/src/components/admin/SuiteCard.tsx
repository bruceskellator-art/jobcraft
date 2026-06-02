import type { EvalRun } from '@/types/eval'
import { scoreColor } from '@/lib/scoreColor'

interface SuiteCardProps {
  suiteName: string
  latestRun: EvalRun
  recentRuns: EvalRun[]
}

const TREND_BAR_COUNT = 4

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function trendBarColor(passRate: number): string {
  if (passRate >= 0.7) {
    if (passRate >= 0.9) return '#059669'
    if (passRate >= 0.8) return '#10b981'
    return '#34d399'
  }
  if (passRate >= 0.4) {
    if (passRate >= 0.6) return '#f59e0b'
    return '#fbbf24'
  }
  return '#f43f5e'
}

export function SuiteCard({ suiteName, latestRun, recentRuns }: SuiteCardProps) {
  const passRate = latestRun.aggregate_scores['pass_rate'] ?? 0
  const chipClass = scoreColor(passRate)
  const chipLabel = passRate >= 1.0 ? 'pass' : chipClass === 'chip-high' ? 'pass' : 'fail'
  const isFailing = passRate < 1.0 && chipClass !== 'chip-high'

  // Trend: take up to TREND_BAR_COUNT most recent runs (oldest first for bar display)
  const trendRuns = [...recentRuns].slice(0, TREND_BAR_COUNT).reverse()

  // Delta vs previous run
  const prevRun = recentRuns[1]
  const prevRate = prevRun?.aggregate_scores['pass_rate'] ?? null
  const delta = prevRate !== null ? passRate - prevRate : null

  const caseCount = latestRun.results.length

  return (
    <div
      className="bg-white border border-zinc-200 rounded-xl p-4"
      style={isFailing ? { borderColor: '#fecdd3' } : undefined}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">
            {suiteName}
          </div>
          <div
            className={`num text-2xl font-semibold mt-1${isFailing ? ' text-rose-600' : ''}`}
          >
            {passRate.toFixed(2)}
          </div>
          <div className="flex items-center gap-1 mt-1">
            {delta !== null ? (
              <>
                <span
                  className={`text-xs font-semibold ${delta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}
                >
                  {delta >= 0 ? '↑' : '↓'} {delta >= 0 ? '+' : ''}
                  {delta.toFixed(2)}
                </span>
                <span className="text-xs text-zinc-400">
                  vs prev {prevRate?.toFixed(2)}
                  {isFailing ? ' ⚠' : ''}
                </span>
              </>
            ) : (
              <span className="text-xs text-zinc-400">first run</span>
            )}
          </div>
        </div>
        <span className={`chip ${chipClass} self-start`}>{chipLabel}</span>
      </div>

      <div className="text-xs text-zinc-400 mt-3 mb-2">
        {caseCount} case{caseCount !== 1 ? 's' : ''} · last run{' '}
        {latestRun.completed_at ? formatTime(latestRun.completed_at) : 'running…'}
      </div>

      {/* Trend bars */}
      <div className="flex items-end gap-1 h-8">
        {trendRuns.map((run) => {
          const rate = run.aggregate_scores['pass_rate'] ?? 0
          const heightPct = Math.max(10, Math.round(rate * 100))
          return (
            <div
              key={run.id}
              className="flex-1 rounded-sm"
              style={{
                height: `${heightPct}%`,
                background: trendBarColor(rate),
              }}
            />
          )
        })}
        {/* Pad with placeholder bars if fewer than TREND_BAR_COUNT runs */}
        {Array.from({ length: Math.max(0, TREND_BAR_COUNT - trendRuns.length) }).map((_, i) => (
          <div
            key={`pad-${i}`}
            className="flex-1 rounded-sm"
            style={{ height: '10%', background: '#e4e4e7' }}
          />
        ))}
      </div>
    </div>
  )
}
