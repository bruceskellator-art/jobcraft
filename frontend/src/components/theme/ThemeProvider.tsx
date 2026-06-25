'use client'

import { ThemeProvider as NextThemesProvider } from 'next-themes'
import type { ComponentProps } from 'react'

/**
 * App-wide theme provider (next-themes).
 *
 * Uses the `class` strategy so Tailwind's `dark:` / `.dark` variant applies,
 * and next-themes injects a blocking inline script to set the theme before
 * first paint — no flash of the wrong theme on load.
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>
}
