// Helpers for rendering job-board source identifiers.
//
// Stored source strings look like: "linkedin", "mycareersfuture",
// "greenhouse:stripe", "lever:ninjavan". Never surface raw lowercase
// identifiers or the "MCF" abbreviation in the UI.

const CATEGORY_LABELS: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  linkedin: 'LinkedIn',
  mycareersfuture: 'MyCareersFuture',
}

export function sourceCategory(source: string): string {
  return source.includes(':') ? source.split(':')[0] : source
}

export function sourceLabel(source: string): string {
  const [cat, token] = source.includes(':') ? source.split(':') : [source, '']
  const catLabel = CATEGORY_LABELS[cat] ?? cat
  if (!token) return catLabel
  const pretty = token.charAt(0).toUpperCase() + token.slice(1)
  return `${catLabel} · ${pretty}`
}

export interface SourceOption {
  value: string
  label: string
}

export const SOURCE_OPTIONS: readonly SourceOption[] = [
  { value: 'all', label: 'All sources' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'mycareersfuture', label: 'MyCareersFuture' },
  { value: 'greenhouse', label: 'Greenhouse' },
  { value: 'lever', label: 'Lever' },
] as const
