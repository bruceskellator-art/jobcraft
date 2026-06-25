'use client'

import { useEffect, useRef } from 'react'
import { useTheme } from 'next-themes'
import { getUiPrefs, putUiPrefs, type ThemePreference } from '@/lib/api'

/**
 * Bridges the local next-themes preference with the server-persisted UI prefs.
 *
 * On mount it pulls the server-saved theme and applies it once (cross-device
 * persistence). After that initial hydration, any local theme change is pushed
 * back to the server. Network failures degrade gracefully to localStorage-only
 * behaviour — the toggle still works offline.
 *
 * Renders nothing.
 */
export function ThemeSync() {
  const { theme, setTheme } = useTheme()
  const isHydrated = useRef(false)
  const lastSynced = useRef<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getUiPrefs(controller.signal)
      .then((prefs) => {
        lastSynced.current = prefs.theme
        setTheme(prefs.theme)
      })
      .catch(() => {
        // Server unreachable — keep whatever next-themes resolved locally.
      })
      .finally(() => {
        isHydrated.current = true
      })
    return () => controller.abort()
  }, [setTheme])

  useEffect(() => {
    if (!isHydrated.current || !theme) return
    if (theme === lastSynced.current) return
    lastSynced.current = theme
    putUiPrefs({ theme: theme as ThemePreference }).catch(() => {
      // Best-effort persistence; local state is still correct.
    })
  }, [theme])

  return null
}
