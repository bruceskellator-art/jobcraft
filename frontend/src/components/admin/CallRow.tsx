'use client'

import { useRouter } from 'next/navigation'
import type { LlmCall } from '@/types/observability'
import { relativeTime } from '@/lib/relativeTime'

interface CallRowProps {
  call: LlmCall
}

function getModelBadgeClass(model: string): string {
  const m = model.toLowerCase()
  if (m.includes('opus')) return 'model-badge model-opus'
  if (m.includes('haiku')) return 'model-badge model-haiku'
  return 'model-badge model-sonnet'
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export function CallRow({ call }: CallRowProps) {
  const router = useRouter()
  const timeAgo = relativeTime(call.called_at)
  const isError = call.error !== null

  function handleClick() {
    router.push(`/admin/calls/${call.id}`)
  }

  return (
    <tr
      className="data-row cursor-pointer"
      onClick={handleClick}
    >
      <td className="px-4 py-2.5 num text-xs text-muted-foreground">{timeAgo}</td>
      <td className="px-2 py-2.5">
        {call.prompt_version_id ? (
          <span className="source-pill">{call.prompt_version_id}</span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-2 py-2.5">
        <span className={getModelBadgeClass(call.model)}>{call.model}</span>
      </td>
      <td className="px-2 py-2.5 num text-right text-xs text-muted-foreground">
        {formatTokens(call.input_tokens)} / {formatTokens(call.output_tokens)}
      </td>
      <td className="px-2 py-2.5 num text-right text-xs">
        {(call.latency_ms / 1000).toFixed(1)}s
      </td>
      <td className="px-2 py-2.5 num text-right text-xs">
        ${call.cost_usd.toFixed(4)}
      </td>
      <td className="px-2 py-2.5">
        {isError ? (
          <span className="badge badge-failed">
            <span className="dot" style={{ background: '#f43f5e' }} />
            error
          </span>
        ) : (
          <span className="badge badge-submitted">
            <span className="dot" style={{ background: '#10b981' }} />
            ok
          </span>
        )}
      </td>
    </tr>
  )
}
