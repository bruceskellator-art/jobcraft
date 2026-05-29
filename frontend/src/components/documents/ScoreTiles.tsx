'use client'

import type { ArtifactScores } from '@/types/artifact'
import { scoreColor } from '@/lib/scoreColor'

interface ScoreTilesProps {
  scores: ArtifactScores
}

const CRITERIA: { key: keyof ArtifactScores; label: string }[] = [
  { key: 'fit', label: 'Fit' },
  { key: 'groundedness', label: 'Grounded' },
  { key: 'ats_keywords', label: 'ATS keywords' },
  { key: 'quantified_impact', label: 'Impact' },
  { key: 'clarity', label: 'Clarity' },
]

export function ScoreTiles({ scores }: ScoreTilesProps) {
  return (
    <div className="grid grid-cols-5 gap-3 text-center">
      {CRITERIA.map(({ key, label }) => {
        const value = scores[key]
        const variant = scoreColor(value)
        return (
          <div key={key} className="bg-zinc-50 rounded-lg p-3">
            <div className="text-xs text-zinc-500 mb-2">{label}</div>
            <span className={`chip ${variant}`}>{value.toFixed(2)}</span>
          </div>
        )
      })}
    </div>
  )
}
