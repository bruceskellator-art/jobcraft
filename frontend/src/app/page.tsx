import Link from 'next/link'
import { StatTile } from '@/components/dashboard/StatTile'
import { TopMatchesList } from '@/components/dashboard/TopMatchesList'
import { QueueHealthPanel } from '@/components/dashboard/QueueHealthPanel'
import { SourcesPanel } from '@/components/dashboard/SourcesPanel'
import { RecentActivity } from '@/components/dashboard/RecentActivity'

const STAT_TILES = [
  {
    id: 'matches',
    label: 'New matches today',
    value: 34,
    subLabel: (
      <>
        <span className="text-xs text-emerald-600 font-semibold">↑ 12%</span>
        <span className="text-xs text-zinc-400">vs yesterday</span>
      </>
    ),
    sparklinePoints: [
      { x: 0, y: 26 }, { x: 10, y: 22 }, { x: 20, y: 24 },
      { x: 30, y: 16 }, { x: 40, y: 18 }, { x: 50, y: 10 }, { x: 64, y: 6 },
    ],
    sparklineColor: '#10b981',
  },
  {
    id: 'queue',
    label: 'In apply queue',
    value: 12,
    subLabel: (
      <span className="text-xs text-amber-600 font-semibold">5 need review</span>
    ),
    sparklinePoints: [
      { x: 0, y: 20 }, { x: 12, y: 18 }, { x: 24, y: 20 },
      { x: 36, y: 16 }, { x: 46, y: 16 }, { x: 54, y: 12 }, { x: 64, y: 14 },
    ],
    sparklineColor: '#f59e0b',
  },
  {
    id: 'submitted',
    label: 'Submitted this week',
    value: 87,
    subLabel: (
      <span className="text-xs text-zinc-400">74 auto · 13 reviewed</span>
    ),
    sparklinePoints: [
      { x: 0, y: 18 }, { x: 10, y: 14 }, { x: 20, y: 16 },
      { x: 30, y: 10 }, { x: 40, y: 12 }, { x: 50, y: 6 }, { x: 64, y: 4 },
    ],
    sparklineColor: '#6366f1',
  },
  {
    id: 'responses',
    label: 'Responses',
    value: 6,
    subLabel: (
      <span className="text-xs text-emerald-600 font-semibold">2 screens booked</span>
    ),
    sparklinePoints: [
      { x: 0, y: 28 }, { x: 16, y: 28 }, { x: 28, y: 24 },
      { x: 36, y: 24 }, { x: 46, y: 22 }, { x: 54, y: 20 }, { x: 64, y: 18 },
    ],
    sparklineColor: '#a1a1aa',
  },
]

export default function DashboardPage() {
  return (
    <>
      {/* Header */}
      <header className="h-14 bg-white border-b border-zinc-200 flex items-center justify-between px-6 sticky top-0 z-10">
        <div>
          <h1 className="text-sm font-semibold">Dashboard</h1>
          <p className="text-xs text-zinc-400">Mon 23 Jun · last scrape 18 min ago</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn btn-ghost">Run scrape</button>
          <Link href="/apply-queue" className="btn btn-primary">
            Review apply queue · 12
          </Link>
        </div>
      </header>

      {/* Body */}
      <div className="p-6 space-y-5">
        {/* Stat tiles */}
        <section className="grid grid-cols-4 gap-4">
          {STAT_TILES.map((tile) => (
            <StatTile
              key={tile.id}
              label={tile.label}
              value={tile.value}
              subLabel={tile.subLabel}
              sparklinePoints={tile.sparklinePoints}
              sparklineColor={tile.sparklineColor}
            />
          ))}
        </section>

        {/* Middle row */}
        <div className="grid grid-cols-3 gap-5">
          <TopMatchesList />
          <div className="space-y-4">
            <QueueHealthPanel />
            <SourcesPanel />
          </div>
        </div>

        {/* Recent activity */}
        <RecentActivity />
      </div>
    </>
  )
}
