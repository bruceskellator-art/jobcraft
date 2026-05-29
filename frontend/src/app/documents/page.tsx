'use client'

import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import { UploadIcon } from 'lucide-react'
import type { Artifact } from '@/types/artifact'
import { listArtifacts, uploadBaseline } from '@/lib/api'
import { ScoreTiles } from '@/components/documents/ScoreTiles'
import { ArtifactRow } from '@/components/documents/ArtifactRow'

const PALETTES = [
  { bg: '#ede9fe', color: '#5b21b6' },
  { bg: '#fce7f3', color: '#be185d' },
  { bg: '#e0e7ff', color: '#4338ca' },
  { bg: '#d1fae5', color: '#065f46' },
  { bg: '#ffedd5', color: '#c2410c' },
  { bg: '#fef9c3', color: '#92400e' },
  { bg: '#e0f2fe', color: '#075985' },
  { bg: '#fce7f3', color: '#9d174d' },
]

function getLogoColors(key: string): { bg: string; color: string } {
  let hash = 0
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  }
  return PALETTES[hash % PALETTES.length]
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
}

export default function DocumentsPage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
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

  const baseline = artifacts.find(a => a.is_baseline) ?? null
  const generated = artifacts.filter(a => !a.is_baseline)

  return (
    <>
      <Toaster />
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Documents</h1>
          <p className="text-xs text-zinc-400">
            Every generated résumé &amp; cover letter, scored against your baseline
          </p>
        </div>
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
      </header>

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
                      {generated.map(artifact => {
                        const key = artifact.job_id ?? artifact.id
                        const logoColors = getLogoColors(key)
                        const initials = getInitials(artifact.job_id ?? 'Unknown')
                        return (
                          <ArtifactRow
                            key={artifact.id}
                            artifact={artifact}
                            baselineScores={baseline?.scores ?? null}
                            jobTitle={
                              artifact.job_id
                                ? `Job ${artifact.job_id.slice(0, 8)}`
                                : 'Unknown job'
                            }
                            jobCompany=""
                            logoColors={logoColors}
                            initials={initials}
                          />
                        )
                      })}
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
