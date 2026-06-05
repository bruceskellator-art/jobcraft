'use client'

import { useState } from 'react'
import type { AnswerBankItem } from '@/types/apply'

interface AnswerBankProps {
  answers: AnswerBankItem[]
  onApprove: (id: string) => Promise<void>
  onCreate: (question: string, answer: string) => Promise<void>
}

export function AnswerBank({ answers, onApprove, onCreate }: AnswerBankProps) {
  const [showForm, setShowForm] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [approvingId, setApprovingId] = useState<string | null>(null)

  async function handleCreate() {
    if (isSaving || !question.trim() || !answer.trim()) return
    setIsSaving(true)
    try {
      await onCreate(question.trim(), answer.trim())
      setQuestion('')
      setAnswer('')
      setShowForm(false)
    } finally {
      setIsSaving(false)
    }
  }

  async function handleApprove(id: string) {
    if (approvingId) return
    setApprovingId(id)
    try {
      await onApprove(id)
    } finally {
      setApprovingId(null)
    }
  }

  return (
    <div className="space-y-2">
      {answers.length === 0 && !showForm && (
        <p className="text-sm text-zinc-400 py-4 text-center">No saved answers yet.</p>
      )}

      {answers.map(item => (
        <div
          key={item.id}
          className={`rounded-lg border px-3 py-2.5 ${
            item.approved
              ? 'border-zinc-200 bg-white'
              : 'border-amber-200 bg-amber-50'
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-zinc-500">{item.question}</p>
              <p className="text-sm text-zinc-800 mt-0.5">{item.answer}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {item.approved ? (
                <span className="toggle-on">
                  approved · {item.reuse_count}x
                </span>
              ) : (
                <>
                  <span className="toggle-off">draft · needs approval</span>
                  <button
                    className="btn btn-ghost text-xs"
                    onClick={() => void handleApprove(item.id)}
                    disabled={approvingId === item.id}
                  >
                    {approvingId === item.id ? 'Approving…' : 'Approve'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      ))}

      {showForm ? (
        <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">Question</label>
            <textarea
              rows={2}
              className="w-full border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              placeholder="e.g. Why do you want to work here?"
              value={question}
              onChange={e => setQuestion(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">Answer</label>
            <textarea
              rows={3}
              className="w-full border border-zinc-200 rounded-lg px-3 py-1.5 text-sm bg-white text-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              placeholder="Your answer…"
              value={answer}
              onChange={e => setAnswer(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button
              className="btn btn-primary text-xs"
              onClick={() => void handleCreate()}
              disabled={isSaving || !question.trim() || !answer.trim()}
            >
              {isSaving ? 'Saving…' : 'Save'}
            </button>
            <button
              className="btn btn-ghost text-xs"
              onClick={() => { setShowForm(false); setQuestion(''); setAnswer('') }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          className="btn btn-ghost text-xs"
          onClick={() => setShowForm(true)}
        >
          + Add answer
        </button>
      )}
    </div>
  )
}
