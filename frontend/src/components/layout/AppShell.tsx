import { Sidebar } from './Sidebar'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-screen">
      <aside className="w-60 bg-white border-r border-zinc-200 fixed inset-y-0 z-20">
        <Sidebar activePage="dashboard" />
      </aside>
      <main className="flex-1 ml-60">{children}</main>
    </div>
  )
}
