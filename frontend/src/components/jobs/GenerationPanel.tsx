'use client'

import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import type { Artifact, StyleConfig } from '@/types/artifact'
import { generateArtifact, listJobArtifacts, ApiError } from '@/lib/api'
import { scoreColor } from '@/lib/scoreColor'

interface GenerationPanelProps {
  jobId: string
}

const DEFAULT_STYLE: StyleConfig = {
  tone: 'professional',
  length: 'standard',
  emphasis: [],
}

function SimpleMarkdown({ content }: { content: string }) {
  const lines = content.split('\n')
  return (
    <div className="text-sm text-zinc-700 space-y-1 leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith('## ')) {
          return <div key={i} className="font-semibold text-zinc-800 mt-2">{line.slice(3)}</div>
        }
        if (line.startsWith('# ')) {
          return <div key={i} className="font-bold text-zinc-900 text-base mt-3">{line.slice(2)}</div>
        }
        if (line.startsWith('- ') || line.startsWith('* ')) {
          return <div key={i} className="pl-3">• {line.slice(2)}</div>
        }
        if (line.trim() === '') {
          return <div key={i} className="h-1" />
        }
        return <div key={i}>{line}</div>
      })}
    </div>
  )
}

function ArtifactPreview({ artifact }: { artifact: Artifact }) {
  const scores = artifact.scores
  const isGrounded = scores ? scores.groundedness >= 0.8 : false
  const groundednessLabel = isGrounded ? 'grounded' : 'review needed'
  const groundednessBorderClass = isGrounded ? 'border-emerald-400' : 'border-rose-400'
  const groundednessTextClass = isGrounded ? 'text-emerald-600' : 'text-rose-600'
  const groundednessBgClass = isGrounded ? '' : 'bg-rose-50/60'

  return (
    <div className="space-y-3">
      {scores && (
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-zinc-400">Groundedness — claim → corpus</span>
          <span
            className={`chip ${scoreColor(scores.groundedness)}`}
            style={{ minWidth: 'auto', padding: '0.1rem 0.4rem', fontSize: '0.65rem' }}
          >
            {groundednessLabel}
          </span>
        </div>
      )}
      <div className={`border-l-2 ${groundednessBorderClass} pl-3 py-0.5 ${groundednessBgClass} rounded-r`}>
        {!isGrounded && (
          <span className={`text-xs ${groundednessTextClass} block mb-1`}>
            ⚠ groundedness score {scores ? scores.groundedness.toFixed(2) : 'n/a'} — review claims before sending
          </span>
        )}
        <SimpleMarkdown content={artifact.content} />
      </div>
      {scores && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          <span className={`chip ${scoreColor(scores.fit)}`} title="Fit">{scores.fit.toFixed(2)}</span>
          <span className={`chip ${scoreColor(scores.groundedness)}`} title="Grounded">{scores.groundedness.toFixed(2)}</span>
          <span className={`chip ${scoreColor(scores.ats_keywords)}`} title="ATS">{scores.ats_keywords.toFixed(2)}</span>
          <span className={`chip ${scoreColor(scores.quantified_impact)}`} title="Impact">{scores.quantified_impact.toFixed(2)}</span>
          <span className={`chip ${scoreColor(scores.clarity)}`} title="Clarity">{scores.clarity.toFixed(2)}</span>
        </div>
      )}
    </div>
  )
}

export function GenerationPanel({ jobId }: GenerationPanelProps) {
  const [style, setStyle] = useState<StyleConfig>(DEFAULT_STYLE)
  const [isGeneratingResume, setIsGeneratingResume] = useState(false)
  const [isGeneratingCover, setIsGeneratingCover] = useState(false)
  const [latestResume, setLatestResume] = useState<Artifact | null>(null)
  const [latestCover, setLatestCover] = useState<Artifact | null>(null)
  const [priorArtifacts, setPriorArtifacts] = useState<Artifact[]>([])
  const [isLoadingPrior, setIsLoadingPrior] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    listJobArtifacts(jobId, controller.signal)
      .then(artifacts => {
        if (controller.signal.aborted) return
        setPriorArtifacts(artifacts)
        setIsLoadingPrior(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (!(err instanceof ApiError && err.status === 404)) {
          // 404 just means no artifacts yet — not an error to surface
        }
        setIsLoadingPrior(false)
      })
    return () => controller.abort()
  }, [jobId])

  async function handleGenerate(kind: 'resume' | 'cover_letter') {
    const isResume = kind === 'resume'
    if (isResume ? isGeneratingResume : isGeneratingCover) return
    if (isResume) setIsGeneratingResume(true)
    else setIsGeneratingCover(true)

    try {
      const artifact = await generateArtifact(jobId, { kind, style })
      if (isResume) setLatestResume(artifact)
      else setLatestCover(artifact)
      setPriorArtifacts(prev => [artifact, ...prev])
      toast.success(`${isResume ? 'Résumé' : 'Cover letter'} generated.`)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Generation failed.')
    } finally {
      if (isResume) setIsGeneratingResume(false)
      else setIsGeneratingCover(false)
    }
  }

  function updateStyle(patch: Partial<StyleConfig>) {
    setStyle(prev => ({ ...prev, ...patch }))
  }

  const isGenerating = isGeneratingResume || isGeneratingCover

  return (
    <div className="space-y-5">
      {/* Generation controls */}
      <section className="bg-white border border-zinc-200 rounded-xl">
        <div className="px-4 py-3 border-b border-zinc-200">
          <h2 className="text-sm font-semibold">Generate documents</h2>
          <p className="text-xs text-zinc-400 mt-0.5">Tailored to this job&apos;s requirements</p>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-zinc-500 uppercase tracking-wide block mb-1">
                Tone
              </label>
              <select
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-1.5 bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                value={style.tone}
                onChange={e => updateStyle({ tone: e.target.value as StyleConfig['tone'] })}
                disabled={isGenerating}
              >
                <option value="professional">Professional</option>
                <option value="conversational">Conversational</option>
                <option value="concise">Concise</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-zinc-500 uppercase tracking-wide block mb-1">
                Length
              </label>
              <select
                className="w-full text-sm border border-zinc-200 rounded-lg px-3 py-1.5 bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                value={style.length}
                onChange={e => updateStyle({ length: e.target.value as StyleConfig['length'] })}
                disabled={isGenerating}
              >
                <option value="brief">Brief</option>
                <option value="standard">Standard</option>
                <option value="detailed">Detailed</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              className="btn btn-ghost flex-1"
              onClick={() => void handleGenerate('resume')}
              disabled={isGenerating}
            >
              {isGeneratingResume ? 'Generating…' : 'Generate résumé'}
            </button>
            <button
              className="btn btn-primary flex-1"
              onClick={() => void handleGenerate('cover_letter')}
              disabled={isGenerating}
            >
              {isGeneratingCover ? 'Generating…' : 'Generate cover letter'}
            </button>
          </div>
        </div>
      </section>

      {/* Latest resume preview */}
      {latestResume && (
        <section className="bg-white border border-zinc-200 rounded-xl">
          <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Tailored résumé</h2>
              {latestResume.prompt_version_id && (
                <p className="text-xs text-zinc-400 mt-0.5 num">{latestResume.prompt_version_id}</p>
              )}
            </div>
            {latestResume.scores && (
              <span className={`chip ${scoreColor(latestResume.scores.groundedness)}`}>
                {latestResume.scores.groundedness.toFixed(2)}
              </span>
            )}
          </div>
          <div className="p-4">
            <ArtifactPreview artifact={latestResume} />
          </div>
          <div className="px-4 pb-4 flex gap-2">
            <button className="btn btn-ghost flex-1">Edit</button>
            <button className="btn btn-primary flex-1">Export PDF</button>
          </div>
        </section>
      )}

      {/* Latest cover letter preview */}
      {latestCover && (
        <section className="bg-white border border-zinc-200 rounded-xl">
          <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Cover letter</h2>
              {latestCover.prompt_version_id && (
                <p className="text-xs text-zinc-400 mt-0.5 num">{latestCover.prompt_version_id}</p>
              )}
            </div>
            {latestCover.scores && (
              <span className={`chip ${scoreColor(latestCover.scores.groundedness)}`}>
                {latestCover.scores.groundedness.toFixed(2)}
              </span>
            )}
          </div>
          <div className="p-4 text-xs text-zinc-500 leading-relaxed">
            <ArtifactPreview artifact={latestCover} />
          </div>
          <div className="px-4 pb-4 flex gap-2">
            <button className="btn btn-ghost flex-1">Edit</button>
            <button className="btn btn-primary flex-1">Export PDF</button>
          </div>
        </section>
      )}

      {/* Prior artifacts */}
      {!isLoadingPrior && priorArtifacts.length > 0 && (
        <section className="bg-white border border-zinc-200 rounded-xl">
          <div className="px-4 py-3 border-b border-zinc-200">
            <h2 className="text-sm font-semibold">Prior generations</h2>
            <p className="text-xs text-zinc-400">
              {priorArtifacts.length} document{priorArtifacts.length !== 1 ? 's' : ''} for this job
            </p>
          </div>
          <ul className="divide-y divide-zinc-100">
            {priorArtifacts.map(a => (
              <li key={a.id} className="px-4 py-3 flex items-center gap-3 data-row">
                <span className={`skill-tag ${a.kind === 'resume' ? 'skill-gen' : 'skill-fe'}`}>
                  {a.kind === 'resume' ? 'Résumé' : 'Cover letter'}
                </span>
                <span className="text-xs text-zinc-400 num flex-1">
                  {new Date(a.created_at).toLocaleDateString('en-SG', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                  })}
                </span>
                {a.scores && (
                  <div className="flex gap-1">
                    <span className={`chip ${scoreColor(a.scores.fit)}`} title="Fit">
                      {a.scores.fit.toFixed(2)}
                    </span>
                    <span className={`chip ${scoreColor(a.scores.groundedness)}`} title="Grounded">
                      {a.scores.groundedness.toFixed(2)}
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
