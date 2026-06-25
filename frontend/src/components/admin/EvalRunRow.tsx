import Link from 'next/link'
import type { EvalRun } from '@/types/eval'
import { scoreColor } from '@/lib/scoreColor'

interface EvalRunRowProps {
  run: EvalRun
  prevPassRate: number | null
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function deriveModelBadge(run: EvalRun): { label: string; cls: string } | null {
  const name = run.prompt_version_id?.toLowerCase() ?? ''
  if (name.includes('opus')) return { label: 'Opus', cls: 'model-opus' }
  if (name.includes('haiku')) return { label: 'Haiku', cls: 'model-haiku' }
  if (name.includes('sonnet')) return { label: 'Sonnet', cls: 'model-sonnet' }
  return null
}

export function EvalRunRow({ run, prevPassRate }: EvalRunRowProps) {
  const passRate = run.aggregate_scores['pass_rate'] ?? 0
  const chipClass = scoreColor(passRate)
  const isFailing = chipClass !== 'chip-high'

  const delta = prevPassRate !== null ? passRate - prevPassRate : null
  const modelBadge = deriveModelBadge(run)

  return (
    <tr
      className="data-row"
      style={isFailing ? { background: '#fff1f2' } : undefined}
    >
      <td className="px-4 py-2.5 font-medium text-foreground">
        <Link href={`/admin/evals/${run.id}`} className="hover:underline">
          {run.suite_name}
        </Link>
      </td>
      <td className="px-2 py-2.5">
        {run.prompt_version_id ? (
          <span className="source-pill">{run.prompt_version_id}</span>
        ) : (
          <span className="text-muted-foreground text-xs">—</span>
        )}
      </td>
      <td className="px-2 py-2.5">
        {modelBadge ? (
          <span className={`model-badge ${modelBadge.cls}`}>{modelBadge.label}</span>
        ) : (
          <span className="text-muted-foreground text-xs">—</span>
        )}
      </td>
      <td
        className={`px-2 py-2.5 num text-right font-semibold${isFailing ? ' text-rose-600' : ''}`}
      >
        {passRate.toFixed(2)}
      </td>
      <td
        className={`px-2 py-2.5 num text-right font-semibold${
          delta === null
            ? ' text-muted-foreground'
            : delta >= 0
              ? ' text-emerald-600'
              : ' text-rose-600'
        }`}
      >
        {delta === null
          ? '—'
          : `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`}
      </td>
      <td className="px-2 py-2.5">
        <span className={`badge ${isFailing ? 'badge-failed' : 'badge-submitted'}`}>
          <span className={`dot ${isFailing ? 'bg-rose-500' : 'bg-emerald-500'}`} />
          {isFailing ? 'fail · below baseline' : 'pass'}
        </span>
      </td>
      <td className="px-2 py-2.5 text-xs text-muted-foreground">
        {formatDateTime(run.started_at)}
      </td>
    </tr>
  )
}
