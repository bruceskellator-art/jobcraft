'use client'

import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import type { Artifact, StyleConfig, ResumeTemplate } from '@/types/artifact'
import {
  generateArtifact,
  listJobArtifacts,
  getTemplates,
  getArtifactPreview,
  downloadArtifactPdf,
  ApiError,
} from '@/lib/api'
import { scoreColor } from '@/lib/scoreColor'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface GenerationPanelProps {
  jobId: string
}

const DEFAULT_STYLE: StyleConfig = {
  tone: 'professional',
  length: 'standard',
  emphasis: [],
}

const A4_W = 794
const A4_H = 1123

function ResumeIframe({ artifactId }: { artifactId: string }) {
  const [html, setHtml] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setIsLoading(true)
    getArtifactPreview(artifactId, controller.signal)
      .then(h => {
        if (!controller.signal.aborted) {
          setHtml(h)
          setIsLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          if (!(err instanceof ApiError && err.status === 0)) {
            toast.error('Could not load preview.')
          }
          setIsLoading(false)
        }
      })
    return () => controller.abort()
  }, [artifactId])

  if (isLoading) {
    return (
      <div
        className="w-full bg-muted border border-border rounded flex items-center justify-center text-xs text-muted-foreground"
        style={{ height: '320px' }}
      >
        Loading preview…
      </div>
    )
  }

  if (!html) {
    return (
      <div
        className="w-full bg-muted border border-border rounded flex items-center justify-center text-xs text-muted-foreground"
        style={{ height: '320px' }}
      >
        Preview unavailable
      </div>
    )
  }

  const containerW = 540
  const scale = containerW / A4_W

  return (
    <div
      className="overflow-hidden rounded border border-border"
      style={{ width: `${containerW}px`, height: `${Math.round(A4_H * scale)}px` }}
    >
      <iframe
        srcDoc={html}
        title="Resume preview"
        sandbox="allow-same-origin"
        style={{
          width: `${A4_W}px`,
          height: `${A4_H}px`,
          border: 'none',
          transformOrigin: '0 0',
          transform: `scale(${scale})`,
          pointerEvents: 'none',
        }}
      />
    </div>
  )
}

function SimpleMarkdown({ content }: { content: string }) {
  const lines = content.split('\n')
  return (
    <div className="text-sm text-foreground space-y-1 leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith('## ')) {
          return <div key={i} className="font-semibold text-foreground mt-2">{line.slice(3)}</div>
        }
        if (line.startsWith('# ')) {
          return <div key={i} className="font-bold text-foreground text-base mt-3">{line.slice(2)}</div>
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

function ArtifactScoreRow({ artifact }: { artifact: Artifact }) {
  const scores = artifact.scores
  const isGrounded = scores ? scores.groundedness >= 0.8 : false
  const groundednessTextClass = isGrounded ? 'text-emerald-600' : 'text-rose-600'
  const groundednessBorderClass = isGrounded ? 'border-emerald-400' : 'border-rose-400'
  const groundednessBgClass = isGrounded ? '' : 'bg-rose-50/60'

  return (
    <div className="space-y-3">
      {scores && (
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-muted-foreground">Groundedness — claim → corpus</span>
          <span
            className={`chip ${scoreColor(scores.groundedness)}`}
            style={{ minWidth: 'auto', padding: '0.1rem 0.4rem', fontSize: '0.65rem' }}
          >
            {isGrounded ? 'grounded' : 'review needed'}
          </span>
        </div>
      )}
      {!isGrounded && (
        <div className={`border-l-2 ${groundednessBorderClass} pl-3 py-0.5 ${groundednessBgClass} rounded-r`}>
          <span className={`text-xs ${groundednessTextClass} block`}>
            ⚠ groundedness {scores ? scores.groundedness.toFixed(2) : 'n/a'} — review claims before sending
          </span>
        </div>
      )}
      {scores && (
        <div className="flex flex-wrap gap-1.5">
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

function TemplatePicker({
  templates,
  selectedId,
  onSelect,
  disabled,
}: {
  templates: ResumeTemplate[]
  selectedId: string
  onSelect: (id: string) => void
  disabled: boolean
}) {
  return (
    <div>
      <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide block mb-1.5">
        Template
      </label>
      <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: 'thin' }}>
        {templates.map(t => (
          <button
            key={t.id}
            type="button"
            disabled={disabled}
            title={t.description}
            onClick={() => onSelect(t.id)}
            className={[
              'flex-none flex flex-col items-center gap-1 rounded-lg border-2 p-1 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-indigo-300',
              selectedId === t.id
                ? 'border-indigo-500 bg-indigo-50'
                : 'border-border bg-card hover:border-border',
              disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
            ].join(' ')}
            style={{ width: '72px' }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={t.thumbnail_url}
              alt={t.name}
              className="w-full rounded object-cover border border-border"
              style={{ height: '90px' }}
              loading="lazy"
            />
            <span className="text-[10px] text-muted-foreground text-center leading-tight line-clamp-2">
              {t.name}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function GenerationPanel({ jobId }: GenerationPanelProps) {
  const [style, setStyle] = useState<StyleConfig>(DEFAULT_STYLE)
  const [selectedTemplateId, setSelectedTemplateId] = useState('standard')
  const [templates, setTemplates] = useState<ResumeTemplate[]>([])
  const [isGeneratingResume, setIsGeneratingResume] = useState(false)
  const [isGeneratingCover, setIsGeneratingCover] = useState(false)
  const [isExportingPdf, setIsExportingPdf] = useState(false)
  const [latestResume, setLatestResume] = useState<Artifact | null>(null)
  const [latestCover, setLatestCover] = useState<Artifact | null>(null)
  const [priorArtifacts, setPriorArtifacts] = useState<Artifact[]>([])
  const [isLoadingPrior, setIsLoadingPrior] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    getTemplates(controller.signal)
      .then(ts => { if (!controller.signal.aborted) setTemplates(ts) })
      .catch(() => { /* non-critical, UI degrades to no picker */ })
    return () => controller.abort()
  }, [])

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
          // 404 = no artifacts yet, not an error to surface
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
      const payload = isResume
        ? { kind, style, template_id: selectedTemplateId }
        : { kind, style }
      const artifact = await generateArtifact(jobId, payload)
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

  async function handleExportPdf(artifact: Artifact) {
    if (isExportingPdf) return
    setIsExportingPdf(true)
    try {
      await downloadArtifactPdf(artifact.id)
      toast.success('PDF downloaded.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'PDF export failed.')
    } finally {
      setIsExportingPdf(false)
    }
  }

  function updateStyle(patch: Partial<StyleConfig>) {
    setStyle(prev => ({ ...prev, ...patch }))
  }

  const isGenerating = isGeneratingResume || isGeneratingCover

  return (
    <div className="space-y-5">
      {/* Generation controls */}
      <section className="bg-card border border-border rounded-xl">
        <div className="px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold">Generate documents</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Tailored to this job&apos;s requirements</p>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide block mb-1">
                Tone
              </label>
              <Select
                value={style.tone}
                onValueChange={(v) => updateStyle({ tone: v as StyleConfig['tone'] })}
                disabled={isGenerating}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="professional">Professional</SelectItem>
                  <SelectItem value="conversational">Conversational</SelectItem>
                  <SelectItem value="concise">Concise</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide block mb-1">
                Length
              </label>
              <Select
                value={style.length}
                onValueChange={(v) => updateStyle({ length: v as StyleConfig['length'] })}
                disabled={isGenerating}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="brief">Brief</SelectItem>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="detailed">Detailed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {templates.length > 0 && (
            <TemplatePicker
              templates={templates}
              selectedId={selectedTemplateId}
              onSelect={setSelectedTemplateId}
              disabled={isGenerating}
            />
          )}
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
        <section className="bg-card border border-border rounded-xl">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Tailored résumé</h2>
              {latestResume.template_id && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Template: {latestResume.template_id}
                  {latestResume.prompt_version_id && (
                    <> · <span className="num">{latestResume.prompt_version_id}</span></>
                  )}
                </p>
              )}
            </div>
            {latestResume.scores && (
              <span className={`chip ${scoreColor(latestResume.scores.groundedness)}`}>
                {latestResume.scores.groundedness.toFixed(2)}
              </span>
            )}
          </div>
          <div className="p-4 space-y-4">
            {latestResume.format === 'json' && latestResume.template_id ? (
              <ResumeIframe artifactId={latestResume.id} />
            ) : (
              <SimpleMarkdown content={latestResume.content} />
            )}
            <ArtifactScoreRow artifact={latestResume} />
          </div>
          <div className="px-4 pb-4 flex gap-2">
            <button className="btn btn-ghost flex-1">Edit</button>
            {latestResume.format === 'json' && (
              <button
                className="btn btn-primary flex-1"
                onClick={() => void handleExportPdf(latestResume)}
                disabled={isExportingPdf}
              >
                {isExportingPdf ? 'Exporting…' : 'Export PDF'}
              </button>
            )}
          </div>
        </section>
      )}

      {/* Latest cover letter preview */}
      {latestCover && (
        <section className="bg-card border border-border rounded-xl">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Cover letter</h2>
              {latestCover.prompt_version_id && (
                <p className="text-xs text-muted-foreground mt-0.5 num">{latestCover.prompt_version_id}</p>
              )}
            </div>
            {latestCover.scores && (
              <span className={`chip ${scoreColor(latestCover.scores.groundedness)}`}>
                {latestCover.scores.groundedness.toFixed(2)}
              </span>
            )}
          </div>
          <div className="p-4 space-y-4">
            <div className="text-xs text-muted-foreground leading-relaxed">
              <SimpleMarkdown content={latestCover.content} />
            </div>
            <ArtifactScoreRow artifact={latestCover} />
          </div>
          <div className="px-4 pb-4">
            <button className="btn btn-ghost w-full">Edit</button>
          </div>
        </section>
      )}

      {/* Prior artifacts */}
      {!isLoadingPrior && priorArtifacts.length > 0 && (
        <section className="bg-card border border-border rounded-xl">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-semibold">Prior generations</h2>
            <p className="text-xs text-muted-foreground">
              {priorArtifacts.length} document{priorArtifacts.length !== 1 ? 's' : ''} for this job
            </p>
          </div>
          <ul className="divide-y divide-border">
            {priorArtifacts.map(a => (
              <li key={a.id} className="px-4 py-3 flex items-center gap-3 data-row">
                <span className={`skill-tag ${a.kind === 'resume' ? 'skill-gen' : 'skill-fe'}`}>
                  {a.kind === 'resume' ? 'Résumé' : 'Cover letter'}
                </span>
                {a.template_id && (
                  <span className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5">
                    {a.template_id}
                  </span>
                )}
                <span className="text-xs text-muted-foreground num flex-1">
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
