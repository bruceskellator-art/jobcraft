'use client'

import { useMemo, useState } from 'react'
import { CheckIcon, ChevronsUpDownIcon, SearchIcon, XIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

interface CompanyMultiSelectProps {
  options: string[]
  selected: string[]
  onChange: (selected: string[]) => void
  disabled?: boolean
}

export function CompanyMultiSelect({
  options,
  selected,
  onChange,
  disabled,
}: CompanyMultiSelectProps) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return options
    return options.filter(name => name.toLowerCase().includes(needle))
  }, [options, filter])

  function toggle(name: string) {
    const next = selected.includes(name)
      ? selected.filter(s => s !== name)
      : [...selected, name]
    onChange(next)
  }

  function remove(name: string) {
    onChange(selected.filter(s => s !== name))
  }

  const triggerLabel =
    selected.length === 0
      ? 'Select companies…'
      : `${selected.length} compan${selected.length === 1 ? 'y' : 'ies'} selected`

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
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
                  selected.length === 0 && 'text-muted-foreground'
                )}
              >
                {triggerLabel}
              </span>
              <ChevronsUpDownIcon className="size-4 shrink-0 text-muted-foreground" />
            </Button>
          }
        />
        <PopoverContent className="w-[var(--anchor-width)] min-w-72 p-0">
          <div className="flex items-center gap-2 border-b border-border px-2.5 py-1.5">
            <SearchIcon className="size-4 shrink-0 text-muted-foreground" />
            <Input
              value={filter}
              onChange={e => setFilter(e.target.value)}
              placeholder="Search companies…"
              className="h-7 border-0 px-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
              autoFocus
            />
            {options.length > 0 && (
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => onChange([...options])}
                  className="cursor-pointer rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted"
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => onChange([])}
                  disabled={selected.length === 0}
                  className="cursor-pointer rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Clear
                </button>
              </div>
            )}
          </div>
          <div
            role="listbox"
            aria-multiselectable="true"
            aria-label="Companies"
            className="max-h-64 overflow-y-auto p-1"
          >
            {filtered.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                No companies found.
              </p>
            ) : (
              filtered.map(name => {
                const isChecked = selected.includes(name)
                return (
                  <button
                    key={name}
                    type="button"
                    role="option"
                    aria-selected={isChecked}
                    onClick={() => toggle(name)}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted"
                  >
                    <span
                      className={cn(
                        'flex size-4 shrink-0 items-center justify-center rounded-[4px] border',
                        isChecked
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input'
                      )}
                    >
                      {isChecked && <CheckIcon className="size-3.5" />}
                    </span>
                    <span className="truncate">{name}</span>
                  </button>
                )
              })
            )}
          </div>
        </PopoverContent>
      </Popover>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map(name => (
            <span
              key={name}
              className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs text-foreground"
            >
              {name}
              <button
                type="button"
                onClick={() => remove(name)}
                disabled={disabled}
                className="cursor-pointer leading-none text-muted-foreground hover:text-foreground disabled:cursor-not-allowed"
                aria-label={`Remove ${name}`}
              >
                <XIcon className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
