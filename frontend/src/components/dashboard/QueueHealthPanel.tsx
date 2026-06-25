import Link from 'next/link'

interface QueueItem {
  label: string
  badgeClass: string
  dotColor: string
  widthPercent: number
  count: number
}

const QUEUE_ITEMS: QueueItem[] = [
  {
    label: 'Auto-submitted',
    badgeClass: 'badge badge-submitted',
    dotColor: 'bg-emerald-500',
    widthPercent: 58,
    count: 7,
  },
  {
    label: 'Needs review',
    badgeClass: 'badge badge-review',
    dotColor: 'bg-amber-500',
    widthPercent: 42,
    count: 5,
  },
  {
    label: 'Blocked',
    badgeClass: 'badge badge-blocked',
    dotColor: 'bg-rose-500',
    widthPercent: 16,
    count: 2,
  },
]

const PROGRESS_COLORS: Record<string, string> = {
  'bg-emerald-500': '#10b981',
  'bg-amber-500': '#f59e0b',
  'bg-rose-500': '#f43f5e',
}

export function QueueHealthPanel() {
  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">Apply queue health</h2>
        <Link
          href="/apply-queue"
          className="text-xs font-medium"
          style={{ color: '#4f46e5' }}
        >
          Open →
        </Link>
      </div>
      <div className="p-4 space-y-3 text-sm">
        {QUEUE_ITEMS.map((item) => (
          <div key={item.label} className="flex items-center gap-2.5">
            <span className={`${item.badgeClass} text-xs w-28 flex-none`}>
              <span className={`dot ${item.dotColor}`} />
              {item.label}
            </span>
            <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${item.widthPercent}%`,
                  background: PROGRESS_COLORS[item.dotColor],
                }}
              />
            </div>
            <span className="num text-xs text-muted-foreground w-4 text-right">
              {item.count}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
