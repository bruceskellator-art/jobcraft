'use client'

import { SearchIcon } from 'lucide-react'
import { SOURCE_OPTIONS } from '@/lib/sources'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export type ScoredFilter = 'all' | 'scored' | 'unscored'
export type SortOption = 'recent' | 'fit'

const SCORED_OPTIONS: { value: ScoredFilter; label: string }[] = [
  { value: 'all', label: 'All jobs' },
  { value: 'scored', label: 'Scored' },
  { value: 'unscored', label: 'Unscored' },
]

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'recent', label: 'Most recent' },
  { value: 'fit', label: 'Best fit' },
]

// Minimum fit-score filter. 'any' clears the constraint; the rest map to a 0..1 floor.
const MIN_FIT_OPTIONS: { value: string; label: string }[] = [
  { value: 'any', label: 'Any fit' },
  { value: '0.5', label: 'Fit ≥ 50%' },
  { value: '0.7', label: 'Fit ≥ 70%' },
  { value: '0.85', label: 'Fit ≥ 85%' },
]

interface JobsToolbarProps {
  searchValue: string
  onSearchChange: (value: string) => void
  source: string
  onSourceChange: (source: string) => void
  scored: ScoredFilter
  onScoredChange: (scored: ScoredFilter) => void
  sort: SortOption
  onSortChange: (sort: SortOption) => void
  minFit: string
  onMinFitChange: (minFit: string) => void
}

export function JobsToolbar({
  searchValue,
  onSearchChange,
  source,
  onSourceChange,
  scored,
  onScoredChange,
  sort,
  onSortChange,
  minFit,
  onMinFitChange,
}: JobsToolbarProps) {
  return (
    <div className="px-6 py-2.5 bg-card border-b border-border flex items-center gap-3 flex-wrap">
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
          className="text-xs border border-border rounded-lg pl-8 pr-3 py-1.5 w-64 focus:outline-none focus:ring-2 focus:ring-ring/40 bg-card"
        />
      </div>

      <div className="h-4 w-px bg-border mx-1" aria-hidden />

      <FilterField label="Source">
        <Select value={source} onValueChange={v => v !== null && onSourceChange(v)}>
          <SelectTrigger size="sm" aria-label="Source" className="text-xs cursor-pointer">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SOURCE_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={opt.value} className="cursor-pointer">
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>

      <FilterField label="Status">
        <Select
          value={scored}
          onValueChange={v => v !== null && onScoredChange(v as ScoredFilter)}
        >
          <SelectTrigger size="sm" aria-label="Status" className="text-xs cursor-pointer">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SCORED_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={opt.value} className="cursor-pointer">
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>

      <FilterField label="Min fit">
        <Select value={minFit} onValueChange={v => v !== null && onMinFitChange(v)}>
          <SelectTrigger size="sm" aria-label="Min fit" className="text-xs cursor-pointer">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MIN_FIT_OPTIONS.map(opt => (
              <SelectItem key={opt.value} value={opt.value} className="cursor-pointer">
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>

      <div className="ml-auto">
        <FilterField label="Sort">
          <Select
            value={sort}
            onValueChange={v => v !== null && onSortChange(v as SortOption)}
          >
            <SelectTrigger size="sm" aria-label="Sort" className="text-xs cursor-pointer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map(opt => (
                <SelectItem key={opt.value} value={opt.value} className="cursor-pointer">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>
      </div>
    </div>
  )
}

interface FilterFieldProps {
  label: string
  children: React.ReactNode
}

function FilterField({ label, children }: FilterFieldProps) {
  // A plain <div>, not a <label>: the child is a shadcn Select (a <button>),
  // which can't be the labelled control of a <label>. Each SelectTrigger
  // carries its own aria-label instead.
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}
