interface SparklinePoint {
  x: number
  y: number
}

interface StatTileProps {
  label: string
  value: string | number
  subLabel: React.ReactNode
  sparklinePoints: SparklinePoint[]
  sparklineColor: string
}

function buildPolylinePoints(points: SparklinePoint[]): string {
  return points.map((p) => `${p.x},${p.y}`).join(' ')
}

export function StatTile({
  label,
  value,
  subLabel,
  sparklinePoints,
  sparklineColor,
}: StatTileProps) {
  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs text-zinc-500 font-medium">{label}</div>
          <div className="num text-2xl font-semibold mt-1">{value}</div>
          <div className="flex items-center gap-1 mt-1">{subLabel}</div>
        </div>
        <svg className="w-16 h-8 mt-0.5" viewBox="0 0 64 32" fill="none">
          <polyline
            points={buildPolylinePoints(sparklinePoints)}
            stroke={sparklineColor}
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>
      </div>
    </div>
  )
}
