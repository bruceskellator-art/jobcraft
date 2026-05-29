'use client'

import type { Artifact, ArtifactScores } from '@/types/artifact'
import { scoreColor } from '@/lib/scoreColor'

interface ArtifactRowProps {
  artifact: Artifact
  baselineScores: ArtifactScores | null
  jobTitle: string
  jobCompany: string
  logoColors: { bg: string; color: string }
  initials: string
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
  logoColors,
  initials,
}: ArtifactRowProps) {
  const scores = artifact.scores
  const isResume = artifact.kind === 'resume'

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

  return (
    <tr className="data-row">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <div
            className="logo-avatar"
            style={{
              background: logoColors.bg,
              color: logoColors.color,
              width: '1.75rem',
              height: '1.75rem',
              fontSize: '0.55rem',
            }}
          >
            {initials}
          </div>
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
        <span className={`skill-tag ${isResume ? 'skill-gen' : 'skill-fe'}`}>
          {isResume ? 'Résumé' : 'Cover letter'}
        </span>
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
        <button className="btn btn-ghost text-xs">View →</button>
      </td>
    </tr>
  )
}
