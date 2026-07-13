import { describe, expect, it, vi } from 'vitest'

import { createMockBridge } from '@/bridge/mockBridge'

describe('mock bridge', () => {
  it('loads defaults that mirror the current Python settings shape', async () => {
    const bridge = createMockBridge()
    const settings = await bridge.getSettings()

    expect(settings).toMatchObject({
      language: 'English (US)',
      model: 'Balanced',
      model_order: 'Speed',
      device_mode: 'auto',
      theme: 'Dark Mode',
      opacity: 100,
      text_format: 'Plain Text',
      hotkey: '<ctrl>+<alt>+d',
    })
    expect(Array.isArray(settings.custom_models)).toBe(true)
  })

  it('returns speed and accuracy model orders', async () => {
    const bridge = createMockBridge()

    await expect(bridge.getModels('Speed')).resolves.toMatchObject([
      { tier: 'Ultra Fast English' },
      { tier: 'Fast' },
      { tier: 'Compact Multilingual' },
      { tier: 'Balanced' },
      { tier: 'Medium Quality' },
      { tier: 'High Accuracy' },
    ])

    await expect(bridge.getModels('Accuracy')).resolves.toMatchObject([
      { tier: 'High Accuracy' },
      { tier: 'Medium Quality' },
      { tier: 'Balanced' },
      { tier: 'Compact Multilingual' },
      { tier: 'Fast' },
      { tier: 'Ultra Fast English' },
    ])
  })

  it('simulates a recording lifecycle and appends a transcript', async () => {
    vi.useFakeTimers()
    const bridge = createMockBridge()
    const states: string[] = []
    bridge.onState((state) => states.push(state.status))

    await bridge.toggleRecording()
    expect((await bridge.getState()).recording).toBe(true)

    await bridge.stopRecording()
    expect((await bridge.getState()).transcribing).toBe(true)

    await vi.advanceTimersByTimeAsync(1600)
    expect((await bridge.getState()).status).toBe('paste-ready')
    expect((await bridge.getHistory())[0]?.text).toContain('Mock transcript')
    expect(states).toContain('recording')
    expect(states).toContain('transcribing')

    vi.useRealTimers()
  })

  it('persists settings and exports history', async () => {
    const bridge = createMockBridge()
    await bridge.saveSettings({ ...(await bridge.getSettings()), model: 'Fast' })
    await expect(bridge.getSettings()).resolves.toMatchObject({ model: 'Fast' })

    await expect(bridge.exportHistory('txt')).resolves.toContain('Project update')
    await expect(bridge.exportHistory('md')).resolves.toContain('- **')
  })
})
