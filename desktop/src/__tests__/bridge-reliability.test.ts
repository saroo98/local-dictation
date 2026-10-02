import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { defaultSettings } from '@/fixtures/settings'

const invokeMock = vi.hoisted(() => vi.fn())
vi.mock('@tauri-apps/api/core', () => ({ invoke: invokeMock, isTauri: () => false }))

import { createPythonBridge } from '@/bridge/pythonBridge'
import { createMockBridge } from '@/bridge/mockBridge'

const idle = {
  recording: false, transcribing: false, waiting_for_target_click: false,
  status: 'idle', latestTranscript: 'retained text', activeModel: 'Balanced', activeLanguage: 'English (US)',
}

describe('bridge reliability', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    invokeMock.mockReset()
    localStorage.clear()
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  })
  afterEach(() => {
    vi.useRealTimers()
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  })

  it('shares and serializes state polling for every subscriber', async () => {
    let resolve!: (value: string) => void
    invokeMock.mockImplementation(() => new Promise<string>((done) => { resolve = done }))
    const bridge = createPythonBridge()
    const first = vi.fn()
    const second = vi.fn()
    const off = [bridge.onState(first), bridge.onState(second)]
    try {
      await vi.advanceTimersByTimeAsync(2500)
      expect(invokeMock).toHaveBeenCalledTimes(1)
      resolve(JSON.stringify({ ok: true, data: idle }))
      await vi.advanceTimersByTimeAsync(0)
      expect(first).toHaveBeenCalledOnce()
      expect(second).toHaveBeenCalledOnce()
    } finally {
      off.forEach((unsubscribe) => unsubscribe())
    }
  })

  it('reports disconnect separately from the last successful operation and recovers', async () => {
    invokeMock.mockResolvedValueOnce(JSON.stringify({ ok: true, data: idle }))
      .mockRejectedValueOnce(new Error('Connection refused'))
      .mockResolvedValue(JSON.stringify({ ok: true, data: idle }))
    const listener = vi.fn()
    const off = createPythonBridge().onState(listener)
    try {
      await vi.advanceTimersByTimeAsync(0)
      await vi.advanceTimersByTimeAsync(750)
      expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({ connected: false, latestTranscript: 'retained text' }))
      await vi.advanceTimersByTimeAsync(750)
      expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({ connected: true, status: 'idle' }))
    } finally { off() }
  })

  it('pauses hidden polling and refreshes immediately when shown', async () => {
    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: idle }))
    const off = createPythonBridge().onState(vi.fn())
    try {
      await vi.advanceTimersByTimeAsync(0)
      Object.defineProperty(document, 'hidden', { configurable: true, value: true })
      document.dispatchEvent(new Event('visibilitychange'))
      const count = invokeMock.mock.calls.length
      await vi.advanceTimersByTimeAsync(3000)
      expect(invokeMock).toHaveBeenCalledTimes(count)
      Object.defineProperty(document, 'hidden', { configurable: true, value: false })
      document.dispatchEvent(new Event('visibilitychange'))
      await vi.advanceTimersByTimeAsync(0)
      expect(invokeMock).toHaveBeenCalledTimes(count + 1)
    } finally { off() }
  })

  it('merges only edited settings fields and preserves concurrent model and position changes', async () => {
    const bridge = createMockBridge()
    await bridge.saveSettings({ bubble_position: [120, 240] })
    await bridge.addCustomModel('Custom', 'C:\\models\\custom')
    await bridge.saveSettings({ language: 'Persian', text_format: 'Markdown (.md)' })
    await expect(bridge.getSettings()).resolves.toMatchObject({
      ...defaultSettings, language: 'Persian', text_format: 'Markdown (.md)', bubble_position: [120, 240],
      custom_models: [{ name: 'Custom', source: 'C:\\models\\custom' }],
    })
  })

  it('guards recording while transcribing and increments history revision after completion', async () => {
    const bridge = createMockBridge()
    await bridge.startRecording()
    await bridge.stopRecording()
    await expect(bridge.startRecording()).rejects.toThrow(/busy|transcrib/i)
    await vi.advanceTimersByTimeAsync(1600)
    expect((await bridge.getState()).history_revision).toBe(1)
  })

  it('rejects unsupported browser filesystem actions and resolves custom model paths', async () => {
    const bridge = createMockBridge()
    await expect(bridge.exportHistory('txt')).rejects.toThrow(/browser|native|Tauri/i)
    await expect(bridge.openModelFolder('Fast')).rejects.toThrow(/browser|native|Tauri/i)
    await bridge.addCustomModel('Custom', 'C:\\models\\custom')
    const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    await bridge.copyModelPath('Custom')
    expect(copy).toHaveBeenLastCalledWith('C:\\models\\custom')
    await expect(bridge.copyModelPath('missing')).rejects.toThrow(/unknown|not found/i)
  })
})
