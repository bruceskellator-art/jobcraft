'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { toast } from 'sonner'
import { UploadIcon, XIcon } from 'lucide-react'
import type { Artifact } from '@/types/artifact'
import { listArtifacts, uploadBaseline, getArtifactPreview, downloadArtifactPdf, ApiError } from '@/lib/api'
import { ScoreTiles } from '@/components/documents/ScoreTiles'
import { ArtifactRow } from '@/components/documents/ArtifactRow'

const A4_W = 794
const A4_H = 1123

function SimpleMarkdown({ content }: { content: string }) {
  const lines = content.split('\n')
  return (
    <div className="text-sm text-zinc-700 space-y-1 leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith('## ')) return <div key={i} className="font-semibold text-zinc-800 mt-2">{line.slice(3)}</div>
        if (line.startsWith('# ')) return <div key={i} className="font-bold text-zinc-900 text-base mt-3">{line.slice(2)}</div>
        if (line.startsWith('- ') || line.startsWith('* ')) return <div key={i} className="pl-3">• {line.slice(2)}</div>
        if (line.trim() === '') return <div key={i} className="h-1" />
        return <div key={i}>{line}</div>
      })}
    </div>
  )
}

function PreviewModal({
  artifact,
  onClose,
}: {
  artifact: Artifact
  onClose: () => void
}) {
  const [html, setHtml] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isDownloading, setIsDownloading] = useState(false)
  const canPreviewHtml = artifact.format === 'json' && Boolean(artifact.template_id)

  useEffect(() => {
    if (!canPreviewHtml) {
      setIsLoading(false)
      return
    }
    const controller = new AbortController()
    getArtifactPreview(artifact.id, controller.signal)
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
  }, [artifact.id, canPreviewHtml])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

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

  const panelW = 640
  const scale = panelW / A4_W

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.45)' }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{ width: `${panelW + 48}px`, maxHeight: '90vh' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-200 flex-none">
          <div>
            <h2 className="text-sm font-semibold">
              {artifact.kind === 'resume' ? 'Résumé preview' : 'Cover letter preview'}
            </h2>
            {artifact.template_id && (
              <p className="text-xs text-zinc-400 mt-0.5">Template: {artifact.template_id}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {artifact.format === 'json' && artifact.template_id && (
              <button
                className="btn btn-primary text-xs"
                onClick={() => void handleDownload()}
                disabled={isDownloading}
              >
                {isDownloading ? 'Exporting…' : 'Export PDF'}
              </button>
            )}
            <button
              className="btn btn-ghost text-xs p-1.5"
              onClick={onClose}
              aria-label="Close preview"
            >
              <XIcon size={14} />
            </button>
          </div>
        </div>

        {/* Modal body */}
        <div className="overflow-y-auto p-6 flex-1">
          {isLoading && (
            <div className="flex items-center justify-center py-16 text-sm text-zinc-400">
              Loading preview…
            </div>
          )}

          {!isLoading && canPreviewHtml && html && (
            <div
              className="mx-auto overflow-hidden rounded border border-zinc-200"
              style={{ width: `${panelW}px`, height: `${Math.round(A4_H * scale)}px` }}
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
          )}

          {!isLoading && !canPreviewHtml && (
            <SimpleMarkdown content={artifact.content} />
          )}

          {!isLoading && canPreviewHtml && !html && (
            <div className="text-sm text-zinc-400 text-center py-8">Preview unavailable.</div>
          )}
        </div>
      </div>
    </div>
  )
}

export function DocumentsView() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    listArtifacts(controller.signal)
      .then(data => {
        if (!controller.signal.aborted) {
          setArtifacts(data)
          setIsLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setLoadError(err instanceof Error ? err.message : 'Failed to load documents.')
          setIsLoading(false)
        }
      })
    return () => controller.abort()
  }, [])

  async function handleUploadBaseline(e: React.ChangeEvent<HTMLInputElement>) {
    if (isUploading) return
    const file = e.target.files?.[0]
    if (!file) return
    setIsUploading(true)
    try {
      const baseline = await uploadBaseline(file)
      setArtifacts(prev => {
        const withoutOldBaseline = prev.filter(a => !a.is_baseline)
        return [baseline, ...withoutOldBaseline]
      })
      toast.success('Baseline résumé uploaded.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleView = useCallback((artifact: Artifact) => {
    setPreviewArtifact(artifact)
  }, [])

  const handleClosePreview = useCallback(() => {
    setPreviewArtifact(null)
  }, [])

  const baseline = artifacts.find(a => a.is_baseline) ?? null
  const generated = artifacts.filter(a => !a.is_baseline)

  return (
    <>
      {previewArtifact && (
        <PreviewModal artifact={previewArtifact} onClose={handleClosePreview} />
      )}

      {/* Action toolbar */}
      <div className="flex items-center justify-end gap-2 px-6 pt-4">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          aria-label="Upload baseline résumé PDF"
          disabled={isUploading}
          onChange={handleUploadBaseline}
        />
        <button
          className="btn btn-ghost"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          <UploadIcon size={13} />
          {isUploading ? 'Uploading…' : baseline ? 'Replace baseline' : 'Upload baseline'}
        </button>
      </div>

      <div className="p-6 space-y-5">
        {isLoading && <div className="empty py-16">Loading documents…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
          </div>
        )}

        {!isLoading && !loadError && (
          <>
            {/* Baseline section */}
            <section className="bg-white border border-zinc-200 rounded-xl">
              <div className="px-4 py-3 border-b border-zinc-200 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg border border-zinc-200 grid place-items-center bg-zinc-50 flex-none">
                  <svg
                    className="w-5 h-5 text-zinc-400"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1.8}
                  >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="8" y1="13" x2="16" y2="13" />
                    <line x1="8" y1="17" x2="16" y2="17" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h2 className="text-sm font-semibold">Baseline résumé — the &quot;before&quot;</h2>
                  {baseline ? (
                    <p className="text-xs text-zinc-400">
                      Uploaded{' '}
                      {new Date(baseline.created_at).toLocaleDateString('en-SG', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })}{' '}
                      · every generated doc is delta&apos;d against this
                    </p>
                  ) : (
                    <p className="text-xs text-zinc-400">
                      No baseline uploaded yet · upload your current résumé to enable scoring
                    </p>
                  )}
                </div>
                {baseline && (
                  <button
                    className="btn btn-ghost text-xs"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploading}
                  >
                    Replace
                  </button>
                )}
              </div>
              <div className="p-4">
                {baseline?.scores ? (
                  <>
                    <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
                      Scores on the same rubric as generated docs
                    </div>
                    <ScoreTiles scores={baseline.scores} />
                  </>
                ) : (
                  <div className="empty py-8">
                    Upload your current résumé to see how generated docs compare
                  </div>
                )}
              </div>
            </section>

            {/* Generated docs table */}
            <section className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
                <h2 className="text-sm font-semibold">Generated documents</h2>
                <span className="text-xs text-zinc-400">
                  {generated.length} doc{generated.length !== 1 ? 's' : ''}
                </span>
              </div>

              {generated.length === 0 ? (
                <div className="empty py-12">
                  No generated documents yet · use the Generate panel on a job to create your first
                </div>
              ) : (
                <>
                  <table className="w-full text-sm">
                    <thead className="bg-zinc-50/80 text-zinc-500 text-xs border-b border-zinc-100">
                      <tr className="text-left">
                        <th className="px-4 py-2.5 font-medium">For job</th>
                        <th className="px-2 py-2.5 font-medium">Type</th>
                        <th className="px-2 py-2.5 font-medium text-center">Fit</th>
                        <th className="px-2 py-2.5 font-medium text-center">Grounded</th>
                        <th className="px-2 py-2.5 font-medium text-center">ATS</th>
                        <th className="px-2 py-2.5 font-medium text-center">Impact</th>
                        <th className="px-2 py-2.5 font-medium text-right">vs baseline</th>
                        <th className="px-2 py-2.5" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100">
                      {generated.map(artifact => (
                        <ArtifactRow
                          key={artifact.id}
                          artifact={artifact}
                          baselineScores={baseline?.scores ?? null}
                          jobTitle={
                            artifact.job_id
                              ? `Job ${artifact.job_id.slice(0, 8)}`
                              : 'Unknown job'
                          }
                          jobCompany={artifact.job_id ?? ''}
                          onView={handleView}
                        />
                      ))}
                    </tbody>
                  </table>
                  <div className="px-4 py-3 border-t border-zinc-100 text-xs text-zinc-400">
                    &quot;View&quot; opens the document with its groundedness trace and a side-by-side diff against your baseline.
                  </div>
                </>
              )}
            </section>
          </>
        )}
      </div>
    </>
  )
}
