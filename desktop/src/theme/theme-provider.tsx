import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from 'react'

import type { ThemeMode, ThemePreset } from '@/bridge/types'

interface ThemeContextValue {
  mode: ThemeMode
  preset: ThemePreset
  setMode: (mode: ThemeMode) => void
  setPreset: (preset: ThemePreset) => void
}

const storageKey = 'local-dictation-theme'
const ThemeContext = createContext<ThemeContextValue | null>(null)

function readInitialTheme(): Pick<ThemeContextValue, 'mode' | 'preset'> {
  const stored = localStorage.getItem(storageKey)
  if (!stored) return { mode: 'system', preset: 'neutral' }

  try {
    const parsed = JSON.parse(stored) as Partial<Pick<ThemeContextValue, 'mode' | 'preset'>>
    return {
      mode: parsed.mode ?? 'system',
      preset: parsed.preset ?? 'neutral',
    }
  } catch {
    return { mode: 'system', preset: 'neutral' }
  }
}

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const initial = readInitialTheme()
  const [mode, setMode] = useState<ThemeMode>(initial.mode)
  const [preset, setPreset] = useState<ThemePreset>(initial.preset)

  useEffect(() => {
    const root = document.documentElement
    const applyTheme = () => {
      const effectiveDark = mode === 'dark' || (mode === 'system' && systemPrefersDark())
      root.classList.toggle('dark', effectiveDark)
      root.classList.toggle('light', !effectiveDark)
      root.classList.remove('theme-neutral', 'theme-green', 'theme-blue')
      root.classList.add(`theme-${preset}`)
      localStorage.setItem(storageKey, JSON.stringify({ mode, preset }))
    }

    applyTheme()
    if (mode !== 'system') return undefined

    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    media?.addEventListener?.('change', applyTheme)
    return () => media?.removeEventListener?.('change', applyTheme)
  }, [mode, preset])

  const value = useMemo(() => ({ mode, preset, setMode, setPreset }), [mode, preset])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
