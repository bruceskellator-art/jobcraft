# JobCraft Frontend

Next.js + React 19 + TypeScript + Tailwind v4 app shell for JobCraft.

## Quickstart

```bash
pnpm install
pnpm dev       # http://localhost:3000
pnpm build     # production build
pnpm lint      # ESLint check
```

## Stack

- **Next.js / React 19** — App Router, Server Components
- **TypeScript** — strict mode, `@/*` import alias
- **Tailwind v4** — CSS-first config in `src/app/globals.css`
- **shadcn/ui** — button, dialog, select, dropdown-menu, tabs, tooltip, checkbox, sonner
- **lucide-react** — icons

## Design tokens

Tokens live in `src/app/globals.css` under `@theme inline`:

| Token | Value |
|---|---|
| `--color-brand-600` | `#4f46e5` (indigo) |
| `--color-signal-low` | `#f43f5e` (rose) |
| `--color-signal-mid` | `#f59e0b` (amber) |
| `--color-signal-high` | `#10b981` (emerald) |
| `--font-family-sans` | Inter |
| `--font-family-mono` | JetBrains Mono |

Bespoke component classes (`.chip`, `.badge`, `.skill-tag`, `.kanban-card`, `.logo-avatar`, `.source-pill`, `.model-badge`, `.toggle-on/off`, `.nav-link`) are defined in `globals.css` and constitute the design language.

## Structure

```
src/
  app/
    globals.css        # Tailwind v4 tokens + bespoke component classes
    layout.tsx         # Root layout with AppShell + TooltipProvider
    page.tsx           # Dashboard home route
  components/
    layout/
      AppShell.tsx     # Sidebar + main wrapper
      Sidebar.tsx      # Nav with all routes
    dashboard/
      StatTile.tsx
      TopMatchesList.tsx
      QueueHealthPanel.tsx
      SourcesPanel.tsx
      RecentActivity.tsx
    ui/                # shadcn primitives
  lib/
    utils.ts
```
