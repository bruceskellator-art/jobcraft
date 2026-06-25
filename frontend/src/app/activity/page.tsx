'use client'

import { Toaster } from '@/components/ui/sonner'
import { ApplyQueueView } from '@/components/apply/ApplyQueueView'

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

        {/* Scraping — placeholder until background scrape lands (Wave 3) */}
        <section>
          <h2 className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground px-1 mb-2">
            Scraping
          </h2>
          <div className="bg-card border border-border rounded-xl p-10 empty">
            Live scrape progress will appear here once background scraping lands. For now,
            run a scrape from Settings — it reports a per-source breakdown when it finishes.
          </div>
        </section>
      </div>
    </>
  )
}
