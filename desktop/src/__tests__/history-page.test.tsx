import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import App from '@/App'

describe('history page', () => {
  it('filters rows and copies transcript text', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<App />)
    const nav = within(screen.getByRole('navigation', { name: 'Main navigation' }))

    await user.click(nav.getByRole('button', { name: 'History' }))
    await user.type(screen.getByPlaceholderText(/search transcripts/i), 'stand-up')

    expect(screen.getByText(/team stand-up/i)).toBeInTheDocument()
    expect(screen.queryByText(/project update/i)).not.toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: /copy transcript/i })[0])
    expect(writeText).toHaveBeenCalled()
  })
})
