'use client'

import { useState } from 'react'
import { Toaster } from '@/components/ui/sonner'
import { ExperienceView } from '@/components/experience/ExperienceView'
import { DocumentsView } from '@/components/documents/DocumentsView'

type WorkspaceTab = 'experience' | 'documents'

const TABS: { id: WorkspaceTab; label: string }[] = [
  { id: 'experience', label: 'Experience' },
  { id: 'documents', label: 'Documents' },
]

export default function WorkspacePage() {
  const [tab, setTab] = useState<WorkspaceTab>('experience')

  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-20">
        <div>
          <h1 className="text-sm font-semibold">Workspace</h1>
          <p className="text-xs text-muted-foreground">
            Your experience corpus and the documents generated from it
          </p>
        </div>
      </header>

      <div className="px-6 flex gap-5 border-b border-border bg-card sticky top-14 z-10">
        {TABS.map(t => {
          const isActive = t.id === tab
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`pb-2.5 pt-3 -mb-px text-sm font-semibold border-b-2 transition-colors ${
                isActive
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'experience' ? <ExperienceView /> : <DocumentsView />}
    </>
  )
}
