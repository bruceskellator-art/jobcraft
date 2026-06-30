import gsap from 'gsap'
import { useGSAP } from '@gsap/react'

// Register the useGSAP plugin once, at module scope. Every animated component
// imports `entrance`/`animateBar` from this module, so importing motion.ts
// guarantees registration has run before any `useGSAP` call — making it robust
// to component load order. Registering is idempotent and safe to repeat.
gsap.registerPlugin(useGSAP)

/**
 * Shared motion tokens. Keep durations short and easing gentle — this is a
 * professional job-board product, so motion should feel like polish, never
 * like a toy. Reuse these everywhere so timing stays consistent.
 */
export const MOTION = {
  durationFast: 0.3,
  duration: 0.4,
  durationSlow: 0.5,
  ease: 'power2.out',
  stagger: 0.06,
  slideDistance: 12,
} as const

/**
 * Whether the current user has requested reduced motion. Returns `false`
 * during SSR (no `window`) so the server render stays neutral; the client
 * effect is the source of truth.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

interface EntranceOptions {
  /** Delay before the entrance starts, in seconds. */
  delay?: number
  /** Per-element stagger when multiple targets are animated. */
  stagger?: number
  /** Vertical slide distance in px (defaults to a subtle 12px). */
  y?: number
  /** Tween duration in seconds. */
  duration?: number
}

/**
 * Fade + subtle slide-in entrance for one or more elements.
 *
 * For reduced-motion users this is a no-op: targets keep their natural,
 * fully-visible state and nothing animates. Returns the created tween (or
 * `null` when skipped) so callers can compose it if needed.
 */
export function entrance(
  targets: gsap.TweenTarget,
  options: EntranceOptions = {},
): gsap.core.Tween | null {
  if (prefersReducedMotion()) return null

  const {
    delay = 0,
    stagger = MOTION.stagger,
    y = MOTION.slideDistance,
    duration = MOTION.duration,
  } = options

  return gsap.from(targets, {
    opacity: 0,
    y,
    duration,
    delay,
    stagger,
    ease: MOTION.ease,
    clearProps: 'opacity,transform',
  })
}

/**
 * Animate the width of progress / score bars from 0 to their target.
 *
 * The target element is expected to already carry its final inline width
 * (e.g. `style={{ width: '72%' }}`); GSAP tweens *from* `0%` up to that
 * resting value, so layout/CLS is driven entirely by the existing markup.
 *
 * For reduced-motion users this is a no-op — the bar simply renders at its
 * final width.
 */
export function animateBar(
  targets: gsap.TweenTarget,
  options: { delay?: number; stagger?: number; duration?: number } = {},
): gsap.core.Tween | null {
  if (prefersReducedMotion()) return null

  const { delay = 0, stagger = 0, duration = MOTION.durationSlow } = options

  return gsap.from(targets, {
    width: 0,
    duration,
    delay,
    stagger,
    ease: MOTION.ease,
  })
}
