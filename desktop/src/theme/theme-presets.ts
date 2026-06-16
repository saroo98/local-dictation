import type { ThemeMode, ThemePreset } from '@/bridge/types'

export const themeModes: { label: string; value: ThemeMode }[] = [
  { label: 'System', value: 'system' },
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
]

export const themePresets: { label: string; value: ThemePreset }[] = [
  { label: 'Neutral', value: 'neutral' },
  { label: 'Green', value: 'green' },
  { label: 'Blue', value: 'blue' },
]
