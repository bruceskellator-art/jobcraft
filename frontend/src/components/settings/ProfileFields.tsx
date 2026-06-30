'use client'

import { useState } from 'react'
import type { ProfileField } from '@/types/apply'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'

interface ProfileFieldsProps {
  fields: ProfileField[]
  onSave: (key: string, value: string, isKnockout: boolean) => Promise<void>
  onAdd: (key: string, value: string, isKnockout: boolean) => Promise<void>
}

interface EditingField {
  key: string
  value: string
}

export function ProfileFields({ fields, onSave, onAdd }: ProfileFieldsProps) {
  const [editing, setEditing] = useState<EditingField | null>(null)
  const [savingKey, setSavingKey] = useState<string | null>(null)

  // New field form state
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newIsKnockout, setNewIsKnockout] = useState(false)
  const [isAdding, setIsAdding] = useState(false)

  async function handleBlur(field: ProfileField) {
    if (!editing || editing.key !== field.key) return
    if (editing.value === field.value) {
      setEditing(null)
      return
    }
    setSavingKey(field.key)
    try {
      await onSave(field.key, editing.value, field.is_knockout)
    } finally {
      setSavingKey(null)
      setEditing(null)
    }
  }

  async function handleAdd() {
    if (isAdding || !newKey.trim() || !newValue.trim()) return
    setIsAdding(true)
    try {
      await onAdd(newKey.trim(), newValue.trim(), newIsKnockout)
      setNewKey('')
      setNewValue('')
      setNewIsKnockout(false)
    } finally {
      setIsAdding(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {fields.map(field => {
          const isKnockout = field.is_knockout
          const currentValue = editing?.key === field.key ? editing.value : field.value
          const isSavingThis = savingKey === field.key

          return (
            <div key={field.key}>
              <label
                className={`block text-xs font-medium mb-1 ${
                  isKnockout ? 'text-amber-700' : 'text-muted-foreground'
                }`}
              >
                {field.key}
                {isKnockout && ' ⚲'}
              </label>
              <Input
                type="text"
                value={currentValue}
                disabled={isSavingThis}
                className={cn(isKnockout && 'border-amber-300')}
                onChange={e => setEditing({ key: field.key, value: e.target.value })}
                onFocus={() => {
                  if (editing?.key !== field.key) {
                    setEditing({ key: field.key, value: field.value })
                  }
                }}
                onBlur={() => void handleBlur(field)}
              />
            </div>
          )
        })}
      </div>

      {/* Add field */}
      <div className="border-t border-border pt-3">
        <p className="text-xs font-medium text-muted-foreground mb-2">Add field</p>
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="text"
            placeholder="Field key"
            value={newKey}
            onChange={e => setNewKey(e.target.value)}
          />
          <Input
            type="text"
            placeholder="Value"
            value={newValue}
            onChange={e => setNewValue(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-3 mt-2">
          <label
            htmlFor="profile-field-knockout"
            className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer"
          >
            <Checkbox
              id="profile-field-knockout"
              checked={newIsKnockout}
              onCheckedChange={checked => setNewIsKnockout(checked)}
              className="cursor-pointer"
            />
            Knockout field
          </label>
          <Button
            size="sm"
            className="cursor-pointer"
            onClick={() => void handleAdd()}
            disabled={isAdding || !newKey.trim() || !newValue.trim()}
          >
            {isAdding ? 'Adding…' : 'Add'}
          </Button>
        </div>
      </div>
    </div>
  )
}
