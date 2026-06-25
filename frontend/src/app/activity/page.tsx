'use client'

import { Toaster } from '@/components/ui/sonner'
import { ApplyQueueView } from '@/components/apply/ApplyQueueView'
import { ScrapingRuns } from '@/components/activity/ScrapingRuns'

export default function ActivityPage() {
  return (
    <>
      <Toaster />
      <header className="h-14 bg-card border-b border-border flex items-center px-6 sticky top-0 z-20">
        <div>
          <h1 className="text-sm font-semibold">Activity</h1>
          <p className="text-xs text-muted-foreground">In-progress tasks — applying and scraping</p>
        </div>
      </header>

      <div className="p-6 space-y-7">
        {/* Applying — the former Apply Queue */}
        <section>
          <h2 className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground px-1 mb-2">
            Applying
          </h2>
          <ApplyQueueView />
        </section>

        {/* Scraping — live background scrape runs */}
        <section>
          <h2 className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground px-1 mb-2">
            Scraping
          </h2>
          <ScrapingRuns />
        </section>
      </div>
    </>
  )
}
