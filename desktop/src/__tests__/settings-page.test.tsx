import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import App from '@/App'

describe('settings page', () => {
  it('saves settings and updates theme controls live', async () => {
    const user = userEvent.setup()
    render(<App />)
    const nav = within(screen.getByRole('navigation', { name: 'Main navigation' }))

    await user.click(nav.getByRole('button', { name: 'Settings' }))
    await chooseLatestSelectOption(user, 'Appearance', 'Dark')
    await chooseLatestSelectOption(user, 'Theme Preset', 'Blue')
    await user.click(screen.getByRole('button', { name: /save changes/i }))

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.classList.contains('theme-blue')).toBe(true)
    expect((await screen.findAllByText(/settings saved/i)).length).toBeGreaterThan(0)
  })
})

async function chooseLatestSelectOption(
  user: ReturnType<typeof userEvent.setup>,
  label: string,
  option: string,
) {
  const triggers = screen.getAllByLabelText(label)
  const trigger = triggers.at(-1)
  expect(trigger).toBeDefined()
  await user.click(trigger!)
  await user.click(await screen.findByRole('option', { name: option }))
}
