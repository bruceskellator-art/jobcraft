'use client'

import { SearchIcon } from 'lucide-react'
import type { JobSource } from '@/types/job'

const SOURCE_OPTIONS: { value: JobSource; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'greenhouse', label: 'Greenhouse' },
  { value: 'lever', label: 'Lever' },
]

interface JobsToolbarProps {
  searchValue: string
  onSearchChange: (value: string) => void
  activeSource: JobSource
  onSourceChange: (source: JobSource) => void
}

export function JobsToolbar({
  searchValue,
  onSearchChange,
  activeSource,
  onSourceChange,
}: JobsToolbarProps) {
  return (
    <div className="px-6 py-2.5 bg-card border-b border-border flex items-center gap-2 flex-wrap">
      <div className="relative">
        <SearchIcon
          size={14}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
        />
        <input
          type="search"
          placeholder="Search title, company, skill…"
          value={searchValue}
          onChange={e => onSearchChange(e.target.value)}
          className="text-xs border border-border rounded-lg pl-8 pr-3 py-1.5 w-64 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-card"
        />
      </div>

      <div className="h-4 w-px bg-border mx-1" aria-hidden />

      <span className="text-xs text-muted-foreground">Source</span>

      {SOURCE_OPTIONS.map(opt => {
        const isActive = activeSource === opt.value
        return (
          <button
            key={opt.value}
            onClick={() => onSourceChange(opt.value)}
            className="btn btn-ghost text-xs"
            style={
              isActive
                ? { background: '#eef2ff', borderColor: '#c7d2fe', color: '#4338ca' }
                : undefined
            }
            aria-pressed={isActive}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
