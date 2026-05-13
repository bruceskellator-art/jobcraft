# JobCraft — Frontend Design Direction

**Date:** 2026-06-23
**Status:** Draft v1
**Owner:** Bruce Ong

> This document is the *contract* the UI is built against. Every screen, component,
> and interaction below maps to a backend capability. We design the frontend first
> because the frontend is what the user does — once the actions are clear, the API
> and data model follow.

---

## 1. Direction (the five questions)

**1. Purpose.** Run a high-volume, low-effort job hunt: discover matched jobs,
inspect fit honestly, generate grounded resumes/cover letters, and apply at scale
through a single review surface — without the user ever touching a job board's UI.

**2. Audience.** A single power user (the job seeker) doing a *repeated daily
workflow*. They open JobCraft to answer three questions fast:
- "What new jobs matched me, and how well?"
- "What's in my apply queue waiting for me?"
- "Is anything stuck or needs a decision?"

**3. Tone.** Utilitarian, dense, calm, technical — *mission control for a job hunt*.
Quiet by default. The interface should feel like an instrument panel, not a
brochure. No hero copy, no marketing sections.

**4. Memorable detail — one calibrated signal scale.** Match score, apply
confidence, and groundedness all share **one** visual language: a calibrated
low → mid → high scale (rose → amber → emerald). The user learns to read one
color/number system everywhere. Numbers render in a monospace face so the UI
reads like a dashboard of instruments.

**5. Constraints.** Next.js 15 + React 19 + Tailwind (target stack). Mockups are
static HTML + Tailwind so they port ~1:1 into React. WCAG AA contrast.
Desktop-first (it's a power tool used at a desk), responsive down to tablet;
mobile is read-only triage, not full workflow.

---

## 2. Visual language

| Token | Value | Use |
|---|---|---|
| Base surface | `zinc-50` | App background |
| Card surface | `white` | Panels, rows, cards |
| Ink | `zinc-900` / `zinc-500` | Primary / secondary text |
| Hairline | `zinc-200` | Borders, dividers |
| Primary action | `indigo-600` | Buttons, active nav, links |
| **Signal — low** | `rose-500` | Score/confidence < 0.4, blocked, errors |
| **Signal — mid** | `amber-500` | 0.4–0.7, needs review, warnings |
| **Signal — high** | `emerald-500` | > 0.7, auto-submitted, grounded |
| UI type | Inter | All text |
| Numeric type | JetBrains Mono | Scores, IDs, counts, costs |

**Palette rules**
- Multi-dimensional neutrals (zinc) + one accent (indigo) + the three signal hues.
- **No** purple gradients, decorative blobs, oversized cards, or card-in-card.
- Color carries meaning. A screen with no signal colors is a screen with nothing
  that needs attention — that's good.

**Layout**
- Persistent left sidebar (primary nav) + main content. No top marketing bar.
- Tables and lists are the primary layout, not cards-in-grids. Dense rows,
  generous-enough line height to scan.
- Fixed-dimension controls: score chips, state badges, and toolbars do not reflow
  when labels/hover appear.

**Motion** — sparing and high-signal only: row state changes (queued → submitted),
streaming generation tokens, queue counters incrementing. No decorative animation.

---

## 3. Information architecture

```
Sidebar
├── Dashboard        pipeline + apply-queue health at a glance
├── Jobs             matched job list (the discovery surface)
│   └── Job detail   extraction, match, gaps, generate
├── Apply Queue ★    the auto-apply review surface (the core new screen)
├── Applications     pipeline / Kanban of submitted apps
├── Experience       the grounded experience corpus
└── Settings
    ├── Sources      enable/configure scrapers + Autopilot toggles
    ├── Answer Bank  reusable screening-question answers
    └── Profile      profile fields (work auth, salary, notice period)
```

★ **Apply Queue** is the screen the whole product is organized around. It is where
the time-saving promise is kept: the user reviews *one* uniform queue instead of
clicking through hundreds of job-board UIs.

---

## 4. Signature components

- **Signal chip** — a fixed-width pill showing a 0–1 value, colored on the
  calibrated scale, mono numerals. Reused for match score, apply confidence,
  groundedness. Learn it once, read it everywhere.
- **Apply-queue row** — job + company + match chip + confidence chip + state badge
  + per-row action (`Approve` / `Edit` / `Skip`). Bulk-select header with
  "Approve all high-confidence" affordance.
- **Field-map review card** — for a queued application: shows every form field the
  agent will submit, the value, and its confidence; uncertain fields highlighted
  amber for the user to confirm. Knockout/work-authorization fields are visually
  pinned and never auto-filled with invented values.
- **Groundedness trace** — generated resume bullets link back to the source
  experience item; ungrounded claims flagged rose for review/removal.
- **State badge** — `queued · auto-filling · needs review · submitted · failed ·
  blocked` — one consistent vocabulary across the app.

---

## 5. Mockups

Static, clickable HTML+Tailwind in `docs/design/mockups/`. Open `dashboard.html`
in a browser; nav links wire the screens together.

| File | Screen | Status |
|---|---|---|
| `dashboard.html` | Dashboard | built |
| `jobs.html` | Matched jobs list | built |
| `job-detail.html` | Job detail (extraction, match, generate) | built |
| `apply-queue.html` | Auto-apply review queue ★ | built |
| `applications.html` | Post-submission Kanban pipeline | built |
| `documents.html` | Generated docs + scoring + baseline before/after | built |
| `experience.html` | Experience corpus | built |
| `settings.html` | Sources / Autopilot / Answer Bank / Profile | built |
| `admin-calls.html` | Observability — LLM call inspector | built |
| `admin-evals.html` | Observability — eval runs & trends | built |
| `admin-prompts.html` | Observability — prompt versions & diff | built |

Shared design system: `mockups/assets/theme.js` (Tailwind tokens),
`components.css` (component styles), `layout.js` (shared sidebar shell — Observability
links grouped under a divider).

---

## 6. Review checklist (per screen)

- [ ] First viewport states the workflow, not the brand.
- [ ] Hierarchy supports scanning + repeated daily use.
- [ ] Signal colors carry meaning; calm where nothing needs attention.
- [ ] Numbers in mono; fixed-dimension chips/badges/toolbars.
- [ ] Knockout/work-auth fields never auto-filled with invented data.
- [ ] AA contrast; labels wrap cleanly on tablet.
- [ ] Ports cleanly to Next.js + Tailwind (no exotic CSS).
