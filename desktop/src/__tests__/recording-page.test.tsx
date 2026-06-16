import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import App from '@/App'

describe('recording page', () => {
  it('starts mock recording from the main action', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /start recording/i }))

    expect(await screen.findByRole('button', { name: /stop recording/i })).toBeInTheDocument()
  })
})
