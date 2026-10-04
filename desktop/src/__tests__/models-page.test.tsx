import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import App from '@/App'

describe('models page', () => {
  it('switches model order and exposes mock actions', async () => {
    const user = userEvent.setup()
    render(<App />)
    const nav = within(screen.getByRole('navigation', { name: 'Main navigation' }))

    await user.click(nav.getByRole('button', { name: 'Models' }))
    expect(screen.getAllByTestId('model-card')[0]).toHaveTextContent('Ultra Fast English')

    await user.click(screen.getByRole('button', { name: /accuracy order/i }))
    expect(screen.getAllByTestId('model-card')[0]).toHaveTextContent('High Accuracy')
    expect(screen.getByRole('button', { name: /add custom model/i })).toBeInTheDocument()
  })
})
