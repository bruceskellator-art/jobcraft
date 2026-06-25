import Link from 'next/link'
import { ThemeToggle } from '@/components/theme/ThemeToggle'

type NavPage =
  | 'dashboard'
  | 'jobs'
  | 'applications'
  | 'activity'
  | 'workspace'
  | 'settings'
  | 'admin-calls'
  | 'admin-evals'
  | 'admin-prompts'

interface NavItem {
  page: NavPage
  href: string
  label: string
  badge?: 'queue'
  iconPath: string
}

interface NavDivider {
  divider: string
}

type NavEntry = NavItem | NavDivider

const NAV: NavEntry[] = [
  {
    page: 'dashboard',
    href: '/',
    label: 'Dashboard',
    iconPath: 'M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z',
  },
  {
    page: 'jobs',
    href: '/jobs',
    label: 'Jobs',
    iconPath:
      'M20 7h-4V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2Zm-6 0h-4V5h4v2Z',
  },
  {
    page: 'applications',
    href: '/applications',
    label: 'Applications',
    iconPath:
      'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm2 16H8v-2h8v2Zm0-4H8v-2h8v2Zm-3-5V3.5L18.5 9H13Z',
  },
  {
    page: 'activity',
    href: '/activity',
    label: 'Activity',
    badge: 'queue',
    iconPath: 'M13 2 3 14h7l-1 8 10-12h-7l1-8Z',
  },
  {
    page: 'workspace',
    href: '/workspace',
    label: 'Workspace',
    iconPath:
      'M12 2 2 7l10 5 10-5-10-5Zm0 7.2L4.2 5.5 12 1.8l7.8 3.7L12 9.2ZM2 12l10 5 10-5-1.9-1 -8.1 4-8.1-4L2 12Zm0 5 10 5 10-5-1.9-1-8.1 4-8.1-4L2 17Z',
  },
  {
    page: 'settings',
    href: '/settings',
    label: 'Settings',
    iconPath:
      'M19.4 13a7.8 7.8 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-1.7-1l-.4-2.6H10.1l-.4 2.6a7.6 7.6 0 0 0-1.7 1l-2.4-1-2 3.4L3.6 11a7.8 7.8 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 1.7 1l.4 2.6h3.8l.4-2.6a7.6 7.6 0 0 0 1.7-1l2.4 1 2-3.4L19.4 13ZM12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5Z',
  },
  { divider: 'Observability' },
  {
    page: 'admin-calls',
    href: '/admin/calls',
    label: 'LLM Calls',
    iconPath: 'M3 5h18v2H3V5Zm0 6h18v2H3v-2Zm0 6h12v2H3v-2Z',
  },
  {
    page: 'admin-evals',
    href: '/admin/evals',
    label: 'Evals',
    iconPath:
      'M3 3h2v18H3V3Zm4 10h3v8H7v-8Zm5-6h3v14h-3V7Zm5 3h3v11h-3V10Z',
  },
  {
    page: 'admin-prompts',
    href: '/admin/prompts',
    label: 'Prompts',
    iconPath: 'M4 4h16v2H4V4Zm0 5h10v2H4V9Zm0 5h16v2H4v-2Zm0 5h10v2H4v-2Z',
  },
]

interface SidebarProps {
  activePage: NavPage
}

function isNavItem(entry: NavEntry): entry is NavItem {
  return 'page' in entry
}

export function Sidebar({ activePage }: SidebarProps) {
  return (
    <div className="h-full flex flex-col">
      {/* Logo + brand */}
      <div className="px-3 py-4 flex items-center gap-2.5 border-b border-border">
        <div
          className="w-8 h-8 rounded-lg text-white grid place-items-center shadow-sm"
          style={{ boxShadow: '0 1px 2px rgba(3,105,161,.35)', background: 'var(--primary)' }}
        >
          <svg
            viewBox="0 0 24 24"
            width={17}
            height={17}
            fill="none"
            stroke="currentColor"
            strokeWidth={2.4}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <div>
          <div className="font-semibold text-sm leading-tight tracking-tight">JobCraft</div>
          <div className="text-[0.7rem] text-muted-foreground leading-tight tracking-wide uppercase">
            SG · job hunt
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {NAV.map((entry, idx) => {
          if (!isNavItem(entry)) {
            return (
              <div
                key={`divider-${idx}`}
                className="px-3 pt-4 pb-1 text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {entry.divider}
              </div>
            )
          }

          const isActive = entry.page === activePage

          return (
            <Link
              key={entry.page}
              href={entry.href}
              className={`nav-link${isActive ? ' active' : ''}`}
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d={entry.iconPath} />
              </svg>
              <span>{entry.label}</span>
              {entry.badge === 'queue' && (
                <span className="num ml-auto text-xs bg-amber-100 text-amber-700 rounded-full px-1.5">
                  12
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* User footer */}
      <div className="p-3 border-t border-border flex items-center gap-2">
        <div className="w-7 h-7 rounded-full bg-muted grid place-items-center text-xs font-semibold text-muted-foreground">
          BO
        </div>
        <div className="text-xs">
          <div className="font-medium text-foreground">Bruce Ong</div>
          <div className="text-muted-foreground">
            Autopilot:{' '}
            <span className="text-emerald-600 font-medium">selective</span>
          </div>
        </div>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </div>
  )
}
