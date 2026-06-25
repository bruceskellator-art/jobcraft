'use client'

import { useState } from 'react'
import type { AutopilotConfig, AutopilotMode } from '@/types/apply'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface AutopilotFormProps {
  initial: AutopilotConfig
  onSave: (config: AutopilotConfig) => Promise<void>
  isSaving: boolean
}

export function AutopilotForm({ initial, onSave, isSaving }: AutopilotFormProps) {
  const [mode, setMode] = useState<AutopilotMode>(initial.mode)
  const [minConfidence, setMinConfidence] = useState(initial.min_confidence)
  const [dailyCap, setDailyCap] = useState(initial.daily_cap)
  const [saveError, setSaveError] = useState<string | null>(null)

  async function handleSave() {
    if (isSaving) return
    setSaveError(null)
    try {
      await onSave({
        ...initial,
        mode,
        min_confidence: minConfidence,
        daily_cap: dailyCap,
      })
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Save failed.')
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">Autopilot mode</label>
          <Select value={mode} onValueChange={(v) => setMode(v as AutopilotMode)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="off">Off</SelectItem>
              <SelectItem value="selective">Selective</SelectItem>
              <SelectItem value="full">Full</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-zinc-400 mt-1">
            {mode === 'off' && 'All applications require manual approval.'}
            {mode === 'selective' && 'Auto-submit only from trusted sources.'}
            {mode === 'full' && 'Auto-submit all high-confidence applications.'}
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">
            Min confidence ({Math.round(minConfidence * 100)}%)
          </label>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={e => setMinConfidence(parseFloat(e.target.value))}
            className="w-full border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">Daily cap</label>
          <input
            type="number"
            min={1}
            max={500}
            step={1}
            value={dailyCap}
            onChange={e => setDailyCap(parseInt(e.target.value, 10))}
            className="w-full border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <p className="text-xs text-zinc-400 mt-1">Max applications submitted per day.</p>
        </div>
      </div>

      {saveError && (
        <p className="text-xs text-red-600">{saveError}</p>
      )}

      <button
        className="btn btn-primary"
        onClick={() => void handleSave()}
        disabled={isSaving}
      >
        {isSaving ? 'Saving…' : 'Save autopilot settings'}
      </button>
    </div>
  )
}
