'use client'

import { useRef, type RefObject } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { entrance } from '@/lib/motion'

// Plugin registration lives in @/lib/motion (imported above via `entrance`),
// which runs `gsap.registerPlugin(useGSAP)` once at module scope.

interface UseEntranceOptions {
  /** Selector (scoped to the container) for the elements to animate in. */
  selector?: string
  /** Delay before the entrance starts, in seconds. */
  delay?: number
  /** Per-element stagger, in seconds. */
  stagger?: number
  /** Vertical slide distance in px. */
  y?: number
  /**
   * Dependencies that, when changed, replay the entrance. Defaults to `[]`
   * (run once on mount). Useful when content arrives after an async fetch.
   */
  deps?: unknown[]
}

/**
 * Scoped fade + slide-in entrance for a container's children.
 *
 * Returns a ref to attach to the container element. Selectors are scoped to
 * that container, GSAP cleanup runs automatically on unmount (via useGSAP),
 * and reduced-motion users get an instant, non-animated render.
 */
export function useEntrance<T extends HTMLElement = HTMLDivElement>({
  selector = '[data-animate]',
  delay = 0,
  stagger,
  y,
  deps = [],
}: UseEntranceOptions = {}): RefObject<T | null> {
  const container = useRef<T>(null)

  useGSAP(
    () => {
      // Scope the query to THIS container — otherwise every mounted useEntrance
      // grabs all `[data-animate]` on the page and they fight, producing the
      // haphazard, out-of-order jerk. The useGSAP `scope` only governs cleanup.
      if (!container.current) return
      const targets = gsap.utils.toArray<HTMLElement>(selector, container.current)
      if (targets.length === 0) return
      entrance(targets, { delay, stagger, y })
    },
    { scope: container, dependencies: deps, revertOnUpdate: true },
  )

  return container
}
