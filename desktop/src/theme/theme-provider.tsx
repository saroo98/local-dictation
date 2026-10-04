import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { isTauri } from '@tauri-apps/api/core'
import { emit, listen } from '@tauri-apps/api/event'

import type { ThemeMode, ThemePreset } from '@/bridge/types'

interface Appearance {
  mode: ThemeMode
  preset: ThemePreset
}

interface ThemeContextValue extends Appearance {
  resolvedMode: 'light' | 'dark'
  setMode: (mode: ThemeMode) => void
  setPreset: (preset: ThemePreset) => void
}

const storageKey = 'local-dictation-theme'
const appearanceEvent = 'local-dictation:appearance'
const ThemeContext = createContext<ThemeContextValue | null>(null)

function readInitialTheme(): Appearance {
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) ?? '{}') as Partial<Appearance>
    return {
      mode: ['system', 'light', 'dark'].includes(stored.mode ?? '') ? stored.mode! : 'system',
      preset: ['neutral', 'green', 'blue'].includes(stored.preset ?? '') ? stored.preset! : 'neutral',
    }
  } catch { return { mode: 'system', preset: 'neutral' } }
}

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearance] = useState(readInitialTheme)
  const [systemDark, setSystemDark] = useState(systemPrefersDark)
  const { mode, preset } = appearance
  const resolvedMode: 'light' | 'dark' = mode === 'dark' || (mode === 'system' && systemDark) ? 'dark' : 'light'

  const changePreference = useCallback((patch: Partial<Appearance>) => {
    // Compose a user edit with the shared current preference, even if this view missed an event.
    const current = readInitialTheme()
    const next = { ...current, ...patch }
    if (current.mode === next.mode && current.preset === next.preset) return
    localStorage.setItem(storageKey, JSON.stringify(next))
    setAppearance(next)
    if (isTauri()) void emit(appearanceEvent, next).catch(() => undefined)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', resolvedMode === 'dark')
    root.classList.toggle('light', resolvedMode === 'light')
    root.classList.remove('theme-neutral', 'theme-green', 'theme-blue')
    root.classList.add('theme-' + preset)
  }, [preset, resolvedMode])

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const applySystemTheme = () => { setSystemDark(media?.matches ?? false) }
    media?.addEventListener?.('change', applySystemTheme)
    return () => { media?.removeEventListener?.('change', applySystemTheme) }
  }, [])

  useEffect(() => {
    let cancelled = false
    let unlisten: (() => void) | undefined
    const refreshPreference = () => {
      const current = readInitialTheme()
      setAppearance((previous) => previous.mode === current.mode && previous.preset === current.preset ? previous : current)
    }
    const storageChanged = (event: StorageEvent) => { if (event.key === storageKey || event.key === null) refreshPreference() }
    window.addEventListener('storage', storageChanged)
    if (isTauri()) {
      void listen<Appearance>(appearanceEvent, () => { if (!cancelled) refreshPreference() })
        .then((off) => { if (cancelled) off(); else { unlisten = off; refreshPreference() } })
        .catch(() => undefined)
    }
    return () => { cancelled = true; unlisten?.(); window.removeEventListener('storage', storageChanged) }
  }, [])

  const value = useMemo(() => ({
    mode, preset, resolvedMode,
    setMode: (next: ThemeMode) => changePreference({ mode: next }),
    setPreset: (next: ThemePreset) => changePreference({ preset: next }),
  }), [changePreference, mode, preset, resolvedMode])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
