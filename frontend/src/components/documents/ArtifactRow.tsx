'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import type { Artifact, ArtifactScores } from '@/types/artifact'
import { scoreColor } from '@/lib/scoreColor'
import { downloadArtifactPdf } from '@/lib/api'
import { CompanyLogo } from '@/components/common/CompanyLogo'

interface ArtifactRowProps {
  artifact: Artifact
  baselineScores: ArtifactScores | null
  jobTitle: string
  jobCompany: string
  onView?: (artifact: Artifact) => void
}

function avgScore(scores: ArtifactScores): number {
  const vals = [
    scores.fit,
    scores.groundedness,
    scores.ats_keywords,
    scores.quantified_impact,
    scores.clarity,
  ]
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

function formatDelta(delta: number): string {
  const sign = delta >= 0 ? '+' : ''
  return `${sign}${delta.toFixed(2)}`
}

export function ArtifactRow({
  artifact,
  baselineScores,
  jobTitle,
  jobCompany,
  onView,
}: ArtifactRowProps) {
  const [isDownloading, setIsDownloading] = useState(false)
  const scores = artifact.scores
  const isResume = artifact.kind === 'resume'
  const canExportPdf = isResume && artifact.format === 'json' && Boolean(artifact.template_id)

  const delta =
    scores && baselineScores
      ? avgScore(scores) - avgScore(baselineScores)
      : null

  function renderDelta() {
    if (!scores) return <span className="text-zinc-300 num">—</span>
    if (delta === null) return <span className="text-zinc-400 num text-xs">new</span>
    const cls = delta >= 0 ? 'text-emerald-600' : 'text-rose-600'
    return <span className={`num font-semibold ${cls}`}>{formatDelta(delta)}</span>
  }

  async function handleDownload() {
    if (isDownloading) return
    setIsDownloading(true)
    try {
      await downloadArtifactPdf(artifact.id)
      toast.success('PDF downloaded.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'PDF export failed.')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <tr className="data-row">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <CompanyLogo company={jobCompany || jobTitle} size="sm" />
          <div>
            <div className="font-semibold text-zinc-800 text-sm">{jobTitle}</div>
            <div className="text-xs text-zinc-400">
              {jobCompany}
              {artifact.prompt_version_id && (
                <>
                  {' · '}
                  <span className="num">{artifact.prompt_version_id}</span>
                </>
              )}
            </div>
          </div>
        </div>
      </td>
      <td className="px-2 py-3">
        <div className="flex flex-col gap-0.5">
          <span className={`skill-tag ${isResume ? 'skill-gen' : 'skill-fe'}`}>
            {isResume ? 'Résumé' : 'Cover letter'}
          </span>
          {artifact.template_id && (
            <span className="text-[10px] text-zinc-400 border border-zinc-200 rounded px-1 py-0.5 w-fit">
              {artifact.template_id}
            </span>
          )}
        </div>
      </td>
      <td className="px-2 py-3 text-center">
        {scores ? (
          <span className={`chip ${scoreColor(scores.fit)}`}>{scores.fit.toFixed(2)}</span>
        ) : (
          <span className="text-zinc-300 num">—</span>
        )}
      </td>
      <td className="px-2 py-3 text-center">
        {scores ? (
          <span className={`chip ${scoreColor(scores.groundedness)}`}>
            {scores.groundedness.toFixed(2)}
          </span>
        ) : (
          <span className="text-zinc-300 num">—</span>
        )}
      </td>
      <td className="px-2 py-3 text-center">
        {scores ? (
          <span className={`chip ${scoreColor(scores.ats_keywords)}`}>
            {scores.ats_keywords.toFixed(2)}
          </span>
        ) : (
          <span className="text-zinc-300 num">—</span>
        )}
      </td>
      <td className="px-2 py-3 text-center">
        {scores ? (
          <span className={`chip ${scoreColor(scores.quantified_impact)}`}>
            {scores.quantified_impact.toFixed(2)}
          </span>
        ) : (
          <span className="text-zinc-300 num">—</span>
        )}
      </td>
      <td className="px-2 py-3 text-right">{renderDelta()}</td>
      <td className="px-2 py-3 text-right">
        <div className="flex items-center justify-end gap-1.5">
          {canExportPdf && (
            <button
              className="btn btn-ghost text-xs"
              onClick={() => void handleDownload()}
              disabled={isDownloading}
              title="Download PDF"
            >
              {isDownloading ? '…' : 'PDF'}
            </button>
          )}
          <button
            className="btn btn-ghost text-xs"
            onClick={() => onView?.(artifact)}
          >
            View →
          </button>
        </div>
      </td>
    </tr>
  )
}
