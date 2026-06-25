interface Source {
  label: string
  dotColor: string
  count: number
  countColor: string
  sublabel?: string
  sublabelColor?: string
}

const SOURCES: Source[] = [
  {
    label: 'MyCareersFuture',
    dotColor: '#10b981',
    count: 421,
    countColor: 'text-emerald-600',
  },
  {
    label: 'Greenhouse / Lever',
    dotColor: '#6366f1',
    count: 208,
    countColor: 'text-emerald-600',
  },
  {
    label: 'LinkedIn',
    dotColor: '#f59e0b',
    count: 96,
    countColor: 'text-amber-600',
    sublabel: 'best-effort',
    sublabelColor: 'text-amber-600',
  },
  {
    label: 'Glints / NodeFlair',
    dotColor: '#a1a1aa',
    count: 63,
    countColor: 'text-muted-foreground',
  },
]

export function SourcesPanel() {
  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold">Sources</h2>
      </div>
      <ul className="p-2">
        {SOURCES.map((source) => (
          <li
            key={source.label}
            className="flex items-center justify-between px-2 py-1.5"
          >
            <div className="flex items-center gap-2">
              <span
                className="col-dot"
                style={{ background: source.dotColor }}
              />
              <span className="text-xs font-medium text-foreground">
                {source.label}
                {source.sublabel && (
                  <>
                    {' '}
                    <span className={`${source.sublabelColor ?? ''}`}>
                      {source.sublabel}
                    </span>
                  </>
                )}
              </span>
            </div>
            <span className={`num text-xs font-semibold ${source.countColor}`}>
              {source.count}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
