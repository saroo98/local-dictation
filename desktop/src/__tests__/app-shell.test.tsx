import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import App from '@/App'

describe('app shell', () => {
  it('renders all six pages and navigates between them', async () => {
    const user = userEvent.setup()
    render(<App />)
    const nav = within(screen.getByRole('navigation', { name: 'Main navigation' }))

    for (const name of ['Recording', 'History', 'Models', 'Settings', 'Exports', 'Help/About']) {
      expect(nav.getByRole('button', { name })).toBeInTheDocument()
    }
    expect(screen.getByText('Stage 5')).toBeInTheDocument()
    expect(screen.getByText(/Tauri can use the packaged backend sidecar/i)).toBeInTheDocument()

    await user.click(nav.getByRole('button', { name: 'Models' }))
    expect(screen.getByRole('heading', { name: 'Models', level: 2 })).toBeInTheDocument()

    await user.click(nav.getByRole('button', { name: 'Settings' }))
    expect(screen.getByRole('heading', { name: 'Settings', level: 2 })).toBeInTheDocument()

    await user.click(nav.getByRole('button', { name: 'Help/About' }))
    expect(screen.getByText(/Stage 5 can start the packaged local backend sidecar/i)).toBeInTheDocument()
  })
})
