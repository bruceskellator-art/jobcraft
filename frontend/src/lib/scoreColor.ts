export type ChipVariant = 'chip-low' | 'chip-mid' | 'chip-high'

export function scoreColor(score: number): ChipVariant {
  if (score >= 0.7) return 'chip-high'
  if (score >= 0.4) return 'chip-mid'
  return 'chip-low'
}
