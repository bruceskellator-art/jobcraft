'use client'

import { useEffect, useState } from 'react'
import { useTheme } from 'next-themes'
import { MoonIcon, SunIcon } from 'lucide-react'

/**
 * Light/dark toggle for the sidebar footer.
 *
 * Renders nothing theme-dependent until mounted to avoid a hydration
 * mismatch (next-themes resolves the theme on the client).
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [isMounted, setIsMounted] = useState(false)

  useEffect(() => {
    setIsMounted(true)
  }, [])

  const isDark = resolvedTheme === 'dark'

  return (
    <button
      type="button"
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title="Toggle theme"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      className="grid place-items-center w-[30px] h-[30px] rounded-lg border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      {isMounted ? (isDark ? <SunIcon size={15} /> : <MoonIcon size={15} />) : <span className="w-[15px] h-[15px]" />}
    </button>
  )
}
