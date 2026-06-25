'use client'

import { usePathname } from 'next/navigation'
import { Sidebar } from './Sidebar'

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

function getActivePage(pathname: string): NavPage {
  if (pathname === '/') return 'dashboard'
  if (pathname.startsWith('/jobs')) return 'jobs'
  if (pathname.startsWith('/applications')) return 'applications'
  // Apply Queue was consolidated into Activity
  if (pathname.startsWith('/activity') || pathname.startsWith('/apply-queue')) return 'activity'
  // Experience + Documents were consolidated into Workspace
  if (
    pathname.startsWith('/workspace') ||
    pathname.startsWith('/experience') ||
    pathname.startsWith('/documents')
  ) {
    return 'workspace'
  }
  if (pathname.startsWith('/settings')) return 'settings'
  if (pathname.startsWith('/admin/calls')) return 'admin-calls'
  if (pathname.startsWith('/admin/evals')) return 'admin-evals'
  if (pathname.startsWith('/admin/prompts')) return 'admin-prompts'
  return 'dashboard'
}

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const activePage = getActivePage(pathname)

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 bg-white border-r border-zinc-200 fixed inset-y-0 z-20">
        <Sidebar activePage={activePage} />
      </aside>
      <main className="flex-1 ml-60">{children}</main>
    </div>
  )
}
