'use client'

import { Toaster } from '@/components/ui/sonner'
import { ExperienceView } from '@/components/experience/ExperienceView'

export default function ExperiencePage() {
  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-10">
        <h1 className="text-sm font-semibold">Experience corpus</h1>
      </header>
      <ExperienceView />
    </>
  )
}
