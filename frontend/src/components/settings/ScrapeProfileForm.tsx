'use client'

import { useState } from 'react'
import type { ScrapeProfileConfig } from '@/types/settings'

interface TagInputProps {
  label: string
  hint?: string
  values: string[]
  onChange: (values: string[]) => void
}

function TagInput({ label, hint, values, onChange }: TagInputProps) {
  const [draft, setDraft] = useState('')

  function commit() {
    const trimmed = draft.trim().replace(/,+$/, '')
    if (!trimmed) return
    const next = trimmed.split(',').map(s => s.trim()).filter(Boolean)
    const unique = next.filter(v => !values.includes(v))
    if (unique.length > 0) onChange([...values, ...unique])
    setDraft('')
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && draft === '' && values.length > 0) {
      onChange(values.slice(0, -1))
    }
  }

  return (
    <div>
      <label className="block text-xs text-muted-foreground mb-1">{label}</label>
      <div className="flex flex-wrap gap-1 border border-border rounded-lg px-2 py-1.5 min-h-[36px] focus-within:ring-1 focus-within:ring-border">
        {values.map((v, i) => (
          <span key={i} className="inline-flex items-center gap-1 bg-muted text-foreground text-xs rounded px-2 py-0.5">
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((_, j) => j !== i))}
              className="text-muted-foreground hover:text-foreground leading-none"
              aria-label={`Remove ${v}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={commit}
          placeholder={values.length === 0 ? 'Type and press Enter' : ''}
          className="flex-1 min-w-[120px] text-xs outline-none bg-transparent placeholder:text-muted-foreground"
        />
      </div>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

interface ScrapeProfileFormProps {
  initial: ScrapeProfileConfig
  onSave: (config: ScrapeProfileConfig) => Promise<void>
  onRun: (config: ScrapeProfileConfig) => Promise<void>
  isSaving: boolean
  isRunning: boolean
}

export function ScrapeProfileForm({ initial, onSave, onRun, isSaving, isRunning }: ScrapeProfileFormProps) {
  const [config, setConfig] = useState<ScrapeProfileConfig>(initial)

  function update<K extends keyof ScrapeProfileConfig>(key: K, value: ScrapeProfileConfig[K]) {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  async function handleRun() {
    await onRun(config)
  }

  return (
    <div className="space-y-3">
      <TagInput
        label="LinkedIn keywords"
        hint="Job title keywords to search LinkedIn — e.g. Forward Deployed Engineer, AI Engineer"
        values={config.linkedin_keywords}
        onChange={v => update('linkedin_keywords', v)}
      />
      <TagInput
        label="MCF keywords"
        hint="Job title keywords to search MyCareersFuture — e.g. Forward Deployed Engineer, AI Engineer"
        values={config.mcf_keywords}
        onChange={v => update('mcf_keywords', v)}
      />
      <TagInput
        label="Greenhouse boards"
        hint="Company board tokens to scrape — e.g. anthropic, stripe, grab (not job titles)"
        values={config.greenhouse_boards}
        onChange={v => update('greenhouse_boards', v)}
      />
      <TagInput
        label="Lever companies"
        hint="Company slugs to scrape — e.g. openai, figma, vercel (not job titles)"
        values={config.lever_companies}
        onChange={v => update('lever_companies', v)}
      />

      <div className="flex items-center gap-4 pt-1">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Lookback days</label>
          <input
            type="number"
            min={1}
            max={90}
            value={config.posted_within_days}
            onChange={e => update('posted_within_days', Math.min(90, Math.max(1, Number(e.target.value))))}
            className="w-20 border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-border"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer pt-4">
          <input
            type="checkbox"
            checked={config.extract}
            onChange={e => update('extract', e.target.checked)}
            className="rounded border-border"
          />
          Extract with AI
          <span className="text-muted-foreground">(slower — populates salary, seniority, tech stack)</span>
        </label>
      </div>

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          disabled={isSaving}
          onClick={() => onSave(config)}
          className="px-3 py-1.5 text-xs font-medium bg-foreground text-white rounded-lg hover:bg-foreground/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          disabled={isRunning}
          onClick={handleRun}
          className="px-3 py-1.5 text-xs font-medium border border-border text-foreground rounded-lg hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
        >
          {isRunning ? (
            <>
              <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Running…
            </>
          ) : 'Run scrape now'}
        </button>
      </div>

      <p className="text-xs text-muted-foreground pt-1">
        Scraping runs in the background — watch live progress on the Activity page.
      </p>
    </div>
  )
}
