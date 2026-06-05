'use client'

import { useState } from 'react'
import type { ProfileField } from '@/types/apply'

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
                  isKnockout ? 'text-amber-700' : 'text-zinc-600'
                }`}
              >
                {field.key}
                {isKnockout && ' ⚲'}
              </label>
              <input
                type="text"
                value={currentValue}
                disabled={isSavingThis}
                className={`w-full border rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                  isKnockout
                    ? 'border-amber-300'
                    : 'border-zinc-200'
                } ${isSavingThis ? 'opacity-50' : ''}`}
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
      <div className="border-t border-zinc-100 pt-3">
        <p className="text-xs font-medium text-zinc-600 mb-2">Add field</p>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="text"
            placeholder="Field key"
            value={newKey}
            onChange={e => setNewKey(e.target.value)}
            className="border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <input
            type="text"
            placeholder="Value"
            value={newValue}
            onChange={e => setNewValue(e.target.value)}
            className="border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="flex items-center gap-3 mt-2">
          <label className="flex items-center gap-1.5 text-xs text-zinc-600 cursor-pointer">
            <input
              type="checkbox"
              checked={newIsKnockout}
              onChange={e => setNewIsKnockout(e.target.checked)}
              className="rounded border-zinc-300"
            />
            Knockout field
          </label>
          <button
            className="btn btn-primary text-xs"
            onClick={() => void handleAdd()}
            disabled={isAdding || !newKey.trim() || !newValue.trim()}
          >
            {isAdding ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  )
}
