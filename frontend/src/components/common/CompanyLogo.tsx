'use client'

import { useState } from 'react'

export interface CompanyLogoProps {
  company: string
  logoUrl?: string | null
  size?: 'sm' | 'md'
  className?: string
}

const PALETTES = [
  { bg: '#ede9fe', color: '#5b21b6' },
  { bg: '#fce7f3', color: '#be185d' },
  { bg: '#e0e7ff', color: '#4338ca' },
  { bg: '#d1fae5', color: '#065f46' },
  { bg: '#ffedd5', color: '#c2410c' },
  { bg: '#fef9c3', color: '#92400e' },
  { bg: '#e0f2fe', color: '#075985' },
  { bg: '#fce7f3', color: '#9d174d' },
] as const

function getLogoColors(company: string): { bg: string; color: string } {
  let hash = 0
  for (let i = 0; i < company.length; i++) {
    hash = (hash * 31 + company.charCodeAt(i)) >>> 0
  }
  return PALETTES[hash % PALETTES.length]
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
}

const SIZE_STYLES: Record<'sm' | 'md', { wh: string; fontSize: string }> = {
  sm: { wh: '1.75rem', fontSize: '0.55rem' },
  md: { wh: '2.25rem', fontSize: '0.625rem' },
}

export function CompanyLogo({
  company,
  logoUrl,
  size = 'sm',
  className = '',
}: CompanyLogoProps) {
  const [imgError, setImgError] = useState(false)

  const { bg, color } = getLogoColors(company)
  const initials = getInitials(company)
  const { wh, fontSize } = SIZE_STYLES[size]

  const sharedStyle: React.CSSProperties = {
    width: wh,
    height: wh,
    flexShrink: 0,
  }

  if (logoUrl && !imgError) {
    return (
      <div
        className={`rounded-lg border border-border bg-muted overflow-hidden flex-none grid place-items-center ${className}`}
        style={sharedStyle}
      >
        <img
          src={logoUrl}
          alt={`${company} logo`}
          className="w-full h-full object-contain"
          onError={() => setImgError(true)}
        />
      </div>
    )
  }

  return (
    <div
      className={`logo-avatar ${className}`}
      style={{
        ...sharedStyle,
        background: bg,
        color,
        fontSize,
      }}
    >
      {initials}
    </div>
  )
}
