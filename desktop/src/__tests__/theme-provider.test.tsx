import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ThemeProvider, useTheme } from '@/theme/theme-provider'

function ThemeProbe() {
  const { mode, preset, setMode, setPreset } = useTheme()

  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="preset">{preset}</span>
      <button type="button" onClick={() => setMode('light')}>
        light
      </button>
      <button type="button" onClick={() => setMode('dark')}>
        dark
      </button>
      <button type="button" onClick={() => setPreset('green')}>
        green
      </button>
      <button type="button" onClick={() => setPreset('blue')}>
        blue
      </button>
    </div>
  )
}

describe('theme provider', () => {
  it('applies mode and preset classes and persists changes', async () => {
    localStorage.clear()
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('mode')).toHaveTextContent('system')
    expect(document.documentElement.classList.contains('theme-neutral')).toBe(true)

    await user.click(screen.getByRole('button', { name: 'dark' }))
    await user.click(screen.getByRole('button', { name: 'green' }))

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.classList.contains('theme-green')).toBe(true)
    expect(localStorage.getItem('local-dictation-theme')).toContain('"mode":"dark"')
  })
})
