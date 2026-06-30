'use client'

import { useEffect, useState } from 'react'

import type { ScrapeProfileConfig } from '@/types/settings'
import { listCuratedCompanies } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { CompanyMultiSelect } from '@/components/settings/CompanyMultiSelect'

const MIN_LOOKBACK_DAYS = 1
const MAX_LOOKBACK_DAYS = 90

interface ScrapeProfileFormProps {
  initial: ScrapeProfileConfig
  onSave: (config: ScrapeProfileConfig) => Promise<void>
  onRun: (config: ScrapeProfileConfig) => Promise<void>
  isSaving: boolean
  isRunning: boolean
}

export function ScrapeProfileForm({
  initial,
  onSave,
  onRun,
  isSaving,
  isRunning,
}: ScrapeProfileFormProps) {
  const [config, setConfig] = useState<ScrapeProfileConfig>(initial)
  const [companies, setCompanies] = useState<string[]>([])

  // Resync local state when the profile is re-fetched/saved upstream. Keyed on
  // the identity of `initial`, so a new profile object (e.g. after a save)
  // reflects here without clobbering edits on unrelated re-renders.
  useEffect(() => {
    setConfig(initial)
  }, [initial])

  useEffect(() => {
    const controller = new AbortController()
    listCuratedCompanies(controller.signal)
      .then(setCompanies)
      .catch(() => {
        // Curated list is optional; the rest of the form still works without it.
      })
    return () => controller.abort()
  }, [])

  function update<K extends keyof ScrapeProfileConfig>(
    key: K,
    value: ScrapeProfileConfig[K]
  ) {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  function handleLookbackChange(raw: string) {
    const parsed = Number(raw)
    if (Number.isNaN(parsed)) return
    const clamped = Math.min(MAX_LOOKBACK_DAYS, Math.max(MIN_LOOKBACK_DAYS, parsed))
    update('posted_within_days', clamped)
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label
          htmlFor="scrape-query"
          className="block text-xs font-medium text-muted-foreground"
        >
          Search query
        </label>
        <Input
          id="scrape-query"
          value={config.query}
          onChange={e => update('query', e.target.value)}
          placeholder="e.g. Forward Deployed Engineer"
        />
        <p className="text-xs text-muted-foreground">
          Searches LinkedIn + MyCareersFuture.
        </p>
      </div>

      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-muted-foreground">
          Target companies <span className="font-normal">(optional)</span>
        </label>
        <CompanyMultiSelect
          options={companies}
          selected={config.companies}
          onChange={v => update('companies', v)}
        />
        <p className="text-xs text-muted-foreground">
          Also scrape these companies&apos; Greenhouse/Lever boards.
        </p>
      </div>

      <div className="space-y-1.5">
        <label
          htmlFor="scrape-location"
          className="block text-xs font-medium text-muted-foreground"
        >
          Location <span className="font-normal">(optional)</span>
        </label>
        <Input
          id="scrape-location"
          value={config.location}
          onChange={e => update('location', e.target.value)}
          placeholder="Singapore"
        />
        <p className="text-xs text-muted-foreground">
          Filter results by city or country.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-6">
        <div className="space-y-1.5">
          <label
            htmlFor="scrape-lookback"
            className="block text-xs font-medium text-muted-foreground"
          >
            Recency (days)
          </label>
          <Input
            id="scrape-lookback"
            type="number"
            min={MIN_LOOKBACK_DAYS}
            max={MAX_LOOKBACK_DAYS}
            value={config.posted_within_days}
            onChange={e => handleLookbackChange(e.target.value)}
            className="w-24"
          />
        </div>

        <label
          htmlFor="scrape-extract"
          className="flex cursor-pointer items-center gap-2 pb-1.5 text-xs text-muted-foreground"
        >
          <Checkbox
            id="scrape-extract"
            checked={config.extract}
            onCheckedChange={checked => update('extract', checked)}
            className="cursor-pointer"
          />
          <span>Extract with AI</span>
          <span className="text-muted-foreground">
            (slower — populates salary, seniority, tech stack)
          </span>
        </label>
      </div>

      <div className="flex gap-2 pt-1">
        <Button
          type="button"
          variant="default"
          disabled={isSaving}
          onClick={() => void onSave(config)}
          className="cursor-pointer"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={isRunning}
          onClick={() => void onRun(config)}
          className="cursor-pointer"
        >
          {isRunning ? (
            <>
              <svg className="size-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>
              Running…
            </>
          ) : (
            'Run scrape now'
          )}
        </Button>
      </div>

      <p className="pt-1 text-xs text-muted-foreground">
        Scraping runs in the background — watch live progress on the Activity page.
      </p>
    </div>
  )
}
