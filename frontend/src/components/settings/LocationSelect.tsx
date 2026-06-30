'use client'

import { useMemo, useState } from 'react'
import { CheckIcon, ChevronsUpDownIcon, SearchIcon, XIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

/** Pre-seeded Singapore-market location options shown in the dropdown. */
const LOCATION_OPTIONS: string[] = [
  'Singapore',
  'Remote',
  'Hybrid',
  'Asia Pacific',
  'Central Singapore',
  'East Singapore',
  'West Singapore',
  'North Singapore',
  'North-East Singapore',
]

interface LocationSelectProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

/**
 * Single-select combobox for job location.
 *
 * - Shows a curated list of Singapore-market locations filtered by the typed
 *   search term.
 * - Any typed value that doesn't match the list can be submitted as a custom
 *   location by pressing Enter or clicking the "Use …" option at the bottom.
 * - An empty/"Any location" choice clears the value.
 */
export function LocationSelect({ value, onChange, disabled }: LocationSelectProps) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return LOCATION_OPTIONS
    return LOCATION_OPTIONS.filter(opt => opt.toLowerCase().includes(needle))
  }, [filter])

  const trimmedFilter = filter.trim()
  // Show a "Use custom value" option when the typed text doesn't exactly match
  // any existing option (case-insensitive) and isn't empty.
  const showCustomOption =
    trimmedFilter.length > 0 &&
    !LOCATION_OPTIONS.some(opt => opt.toLowerCase() === trimmedFilter.toLowerCase())

  function select(next: string) {
    onChange(next)
    setFilter('')
    setOpen(false)
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation()
    onChange('')
    setFilter('')
  }

  const triggerLabel = value || 'Any location'

  return (
    <Popover open={open} onOpenChange={(next) => {
      setOpen(next)
      if (!next) setFilter('')
    }}>
      <PopoverTrigger
        disabled={disabled}
        render={
          <Button
            type="button"
            variant="outline"
            className="w-full cursor-pointer justify-between font-normal"
          >
            <span
              className={cn(
                'truncate',
                !value && 'text-muted-foreground',
              )}
            >
              {triggerLabel}
            </span>
            <span className="flex items-center gap-1 shrink-0">
              {value && (
                <span
                  role="button"
                  tabIndex={0}
                  aria-label="Clear location"
                  onClick={clear}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChange(''); setFilter('') } }}
                  className="cursor-pointer text-muted-foreground hover:text-foreground"
                >
                  <XIcon className="size-3.5" />
                </span>
              )}
              <ChevronsUpDownIcon className="size-4 text-muted-foreground" />
            </span>
          </Button>
        }
      />
      <PopoverContent className="w-[var(--anchor-width)] min-w-64 p-0">
        {/* Search input */}
        <div className="flex items-center gap-2 border-b border-border px-2.5 py-1.5">
          <SearchIcon className="size-4 shrink-0 text-muted-foreground" />
          <Input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && trimmedFilter) {
                select(trimmedFilter)
              }
            }}
            placeholder="Search or type a location…"
            className="h-7 border-0 px-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
            autoFocus
          />
        </div>

        <div
          role="listbox"
          aria-label="Location options"
          className="max-h-64 overflow-y-auto p-1"
        >
          {/* Any location / clear option */}
          <button
            type="button"
            role="option"
            aria-selected={!value}
            onClick={() => select('')}
            className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted text-muted-foreground italic"
          >
            <span className={cn('flex size-4 shrink-0 items-center justify-center rounded-[4px] border', !value ? 'border-primary bg-primary text-primary-foreground' : 'border-input')}>
              {!value && <CheckIcon className="size-3.5" />}
            </span>
            Any location
          </button>

          {filtered.map(opt => {
            const isSelected = value === opt
            return (
              <button
                key={opt}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => select(opt)}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted"
              >
                <span
                  className={cn(
                    'flex size-4 shrink-0 items-center justify-center rounded-[4px] border',
                    isSelected
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-input',
                  )}
                >
                  {isSelected && <CheckIcon className="size-3.5" />}
                </span>
                <span className="truncate">{opt}</span>
              </button>
            )
          })}

          {filtered.length === 0 && !showCustomOption && (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">
              No locations found.
            </p>
          )}

          {/* Custom value option — shown when typed text doesn't match any preset */}
          {showCustomOption && (
            <button
              type="button"
              role="option"
              aria-selected={value === trimmedFilter}
              onClick={() => select(trimmedFilter)}
              className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted"
            >
              <span
                className={cn(
                  'flex size-4 shrink-0 items-center justify-center rounded-[4px] border',
                  value === trimmedFilter
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-input',
                )}
              >
                {value === trimmedFilter && <CheckIcon className="size-3.5" />}
              </span>
              <span className="truncate">
                Use &ldquo;{trimmedFilter}&rdquo;
              </span>
            </button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
