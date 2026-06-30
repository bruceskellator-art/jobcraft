'use client'

import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { Toaster } from '@/components/ui/sonner'
import type { AutopilotConfig, AnswerBankItem, ProfileField } from '@/types/apply'
import type { ScrapeProfileConfig } from '@/types/settings'
import {
  getAutopilot,
  putAutopilot,
  getProfileFields,
  putProfileField,
  listAnswers,
  createAnswer,
  approveAnswer,
  getScrapeProfile,
  putScrapeProfile,
  enqueueScrape,
} from '@/lib/api'
import { AutopilotForm } from '@/components/settings/AutopilotForm'
import { AnswerBank } from '@/components/settings/AnswerBank'
import { ProfileFields } from '@/components/settings/ProfileFields'
import { EmailSync } from '@/components/settings/EmailSync'
import { ScrapeProfileForm } from '@/components/settings/ScrapeProfileForm'

const SOURCES = [
  { name: 'LinkedIn', key: 'linkedin', trusted: true },
  { name: 'Greenhouse', key: 'greenhouse', trusted: true },
  { name: 'Lever', key: 'lever', trusted: true },
  { name: 'MyCareersFuture', key: 'mycareersfuture', trusted: false },
]

export default function SettingsPage() {
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autopilot, setAutopilot] = useState<AutopilotConfig | null>(null)
  const [profileFields, setProfileFields] = useState<ProfileField[]>([])
  const [answers, setAnswers] = useState<AnswerBankItem[]>([])

  const [isSavingAutopilot, setIsSavingAutopilot] = useState(false)
  const [scrapeProfile, setScrapeProfile] = useState<ScrapeProfileConfig | null>(null)
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [isRunning, setIsRunning] = useState(false)

  const loadAll = useCallback((signal: AbortSignal) => {
    Promise.all([
      getAutopilot(signal),
      getProfileFields(signal),
      listAnswers(signal),
      getScrapeProfile(signal),
    ])
      .then(([ap, fields, ans, profile]) => {
        if (signal.aborted) return
        setAutopilot(ap)
        setProfileFields(fields)
        setAnswers(ans)
        setScrapeProfile(profile)
        setIsLoading(false)
      })
      .catch((err: unknown) => {
        if (signal.aborted) return
        setLoadError(err instanceof Error ? err.message : 'Failed to load settings.')
        setIsLoading(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadAll(controller.signal)
    return () => controller.abort()
  }, [loadAll])

  async function handleSaveProfile(config: ScrapeProfileConfig) {
    if (isSavingProfile) return
    setIsSavingProfile(true)
    try {
      const updated = await putScrapeProfile(config)
      setScrapeProfile(updated)
      toast.success('Scrape profile saved.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to save scrape profile.')
      throw err
    } finally {
      setIsSavingProfile(false)
    }
  }

  async function handleRunScrape(config: ScrapeProfileConfig): Promise<void> {
    setIsRunning(true)
    try {
      await enqueueScrape(config)
      toast.success('Scrape started — track progress in Activity.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Scrape failed.')
      throw err
    } finally {
      setIsRunning(false)
    }
  }

  async function handleSaveAutopilot(config: AutopilotConfig) {
    if (isSavingAutopilot) return
    setIsSavingAutopilot(true)
    try {
      const updated = await putAutopilot(config)
      setAutopilot(updated)
      toast.success('Autopilot settings saved.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to save autopilot.')
      throw err
    } finally {
      setIsSavingAutopilot(false)
    }
  }

  async function handleApproveAnswer(id: string) {
    const updated = await approveAnswer(id, true)
    setAnswers(prev => prev.map(a => a.id === id ? updated : a))
  }

  async function handleCreateAnswer(question: string, answer: string) {
    const created = await createAnswer(question, answer)
    setAnswers(prev => [...prev, created])
  }

  async function handleSaveField(key: string, value: string, isKnockout: boolean) {
    const updated = await putProfileField(key, value, isKnockout)
    setProfileFields(prev =>
      prev.map(f => f.key === key ? updated : f)
    )
  }

  async function handleAddField(key: string, value: string, isKnockout: boolean) {
    const created = await putProfileField(key, value, isKnockout)
    setProfileFields(prev => {
      const exists = prev.some(f => f.key === created.key)
      if (exists) return prev.map(f => f.key === created.key ? created : f)
      return [...prev, created]
    })
  }

  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Settings</h1>
          <p className="text-xs text-muted-foreground">Autopilot, answer bank, and profile fields</p>
        </div>
      </header>

      <div className="p-6 max-w-3xl space-y-5">
        {isLoading && <div className="empty py-16">Loading settings…</div>}

        {!isLoading && loadError && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
            {loadError}
            <button
              onClick={() => {
                const controller = new AbortController()
                loadAll(controller.signal)
              }}
              className="ml-2 underline text-red-600 hover:text-red-800"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !loadError && (
          <>
            {/* Scrape Profile */}
            <section className="bg-card border border-border rounded-xl p-4">
              <h2 className="text-sm font-semibold mb-3">Scrape profile</h2>
              {scrapeProfile && (
                <ScrapeProfileForm
                  initial={scrapeProfile}
                  onSave={handleSaveProfile}
                  onRun={handleRunScrape}
                  isSaving={isSavingProfile}
                  isRunning={isRunning}
                />
              )}
            </section>

            {/* Sources & Autopilot */}
            <section className="bg-card border border-border rounded-xl p-4 space-y-4">
              <h2 className="text-sm font-semibold">Sources &amp; Autopilot</h2>

              <table className="w-full text-sm">
                <thead className="bg-muted/80 text-muted-foreground text-xs border-b border-border">
                  <tr className="text-left">
                    <th className="px-3 py-2 font-medium">Source</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Trusted</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {SOURCES.map(src => (
                    <tr key={src.key} className="data-row">
                      <td className="px-3 py-2 font-medium text-foreground">{src.name}</td>
                      <td className="px-3 py-2">
                        <span className="toggle-on">active</span>
                      </td>
                      <td className="px-3 py-2">
                        {src.trusted
                          ? <span className="toggle-on">trusted</span>
                          : <span className="toggle-off">untrusted</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {autopilot && (
                <AutopilotForm
                  initial={autopilot}
                  onSave={handleSaveAutopilot}
                  isSaving={isSavingAutopilot}
                />
              )}
            </section>

            {/* Answer Bank */}
            <section className="bg-card border border-border rounded-xl p-4">
              <h2 className="text-sm font-semibold mb-3">Answer Bank</h2>
              <AnswerBank
                answers={answers}
                onApprove={handleApproveAnswer}
                onCreate={handleCreateAnswer}
              />
            </section>

            {/* Profile Fields */}
            <section className="bg-card border border-border rounded-xl p-4">
              <h2 className="text-sm font-semibold mb-3">Profile Fields</h2>
              <ProfileFields
                fields={profileFields}
                onSave={handleSaveField}
                onAdd={handleAddField}
              />
            </section>

            {/* Email Sync */}
            <EmailSync />
          </>
        )}
      </div>
    </>
  )
}
