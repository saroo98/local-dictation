import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BridgeContext } from '@/bridge/bridgeContext'
import { BackendStatusContext, type BackendStatusContextValue } from '@/bridge/BackendStatusContext'
import { createMockBridge } from '@/bridge/mockBridge'
import { createPythonBridge } from '@/bridge/pythonBridge'
import type { BackendStatus } from '@/bridge/types'
import { TauriBubbleController } from '@/components/dictation/TauriBubbleController'
import { FloatingBubbleSurface } from '@/components/dictation/FloatingBubbleSurface'
import { QuickHistoryPopoverSurface } from '@/components/dictation/QuickHistoryPopoverSurface'
import { ThemeProvider, useTheme } from '@/theme/theme-provider'

const invokeMock = vi.hoisted(() => vi.fn())
const emitMock = vi.hoisted(() => vi.fn(async () => undefined))
const movedMock = vi.hoisted(() => vi.fn())
const handlers = vi.hoisted(() => new Map<string, (event: { payload: unknown }) => void>())
vi.mock('@tauri-apps/api/core', () => ({ invoke: invokeMock, isTauri: () => true }))
vi.mock('@tauri-apps/api/event', () => ({
  emit: emitMock,
  listen: vi.fn(async (name: string, callback: (event: { payload: unknown }) => void) => {
    handlers.set(name, callback)
    return () => { handlers.delete(name) }
  }),
}))
vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({ onMoved: movedMock, startDragging: vi.fn(async () => undefined) }),
}))

function context(status: BackendStatus): BackendStatusContextValue {
  return { backendStatus: status, refreshBackendStatus: async () => status, startBackend: async () => status, stopBackend: async () => status, restartBackend: async () => status }
}

function AppearanceProbe() {
  const { mode, preset, setPreset } = useTheme()
  return <><span>{mode}/{preset}</span><button onClick={() => setPreset('green')}>Green</button></>
}

describe('native frontend contracts with controlled native calls', () => {
  beforeEach(() => { invokeMock.mockReset(); emitMock.mockClear(); movedMock.mockReset(); movedMock.mockResolvedValue(() => {}); handlers.clear(); localStorage.clear() })
  afterEach(() => { vi.useRealTimers() })

  it('starts no state poll in a hidden native window and refreshes on show', async () => {
    vi.useFakeTimers()
    const state = await createMockBridge().getState()
    invokeMock.mockImplementation(async (command: string) => command === 'current_window_visible' ? false : JSON.stringify({ ok: true, data: state }))
    const off = createPythonBridge().onState(vi.fn())
    try {
      await vi.advanceTimersByTimeAsync(2000)
      expect(invokeMock.mock.calls.filter(([command]) => command === 'bridge_call')).toHaveLength(0)
      handlers.get('local-dictation:window-visibility')!({ payload: true })
      await vi.advanceTimersByTimeAsync(0)
      expect(invokeMock.mock.calls.filter(([command]) => command === 'bridge_call')).toHaveLength(1)
      handlers.get('local-dictation:window-visibility')!({ payload: false })
      await vi.advanceTimersByTimeAsync(2000)
      expect(invokeMock.mock.calls.filter(([command]) => command === 'bridge_call')).toHaveLength(1)
    } finally { off() }
  })

  it('keeps a newer visibility event when the initial native query completes late', async () => {
    vi.useFakeTimers()
    let resolveVisible!: (visible: boolean) => void
    const state = await createMockBridge().getState()
    invokeMock.mockImplementation((command: string) => command === 'current_window_visible'
      ? new Promise<boolean>((resolve) => { resolveVisible = resolve })
      : Promise.resolve(JSON.stringify({ ok: true, data: state })))
    const off = createPythonBridge().onState(vi.fn())
    try {
      await vi.advanceTimersByTimeAsync(0)
      handlers.get('local-dictation:window-visibility')!({ payload: true })
      await vi.advanceTimersByTimeAsync(0)
      resolveVisible(false)
      await vi.advanceTimersByTimeAsync(751)
      expect(invokeMock.mock.calls.filter(([command]) => command === 'bridge_call')).toHaveLength(2)
    } finally { off() }
  })

  it('uses narrow picker, settings patch and resource retry command envelopes', async () => {
    const bridge = createPythonBridge()
    invokeMock.mockResolvedValueOnce('C:\\exports')
    await expect(bridge.pickExportFolder()).resolves.toBe('C:\\exports')
    expect(invokeMock).toHaveBeenLastCalledWith('pick_export_folder')
    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: await createMockBridge().getSettings() }))
    await bridge.saveSettings({ language: 'Persian' })
    expect(JSON.parse(invokeMock.mock.calls.at(-1)![1].request)).toEqual({ cmd: 'set-settings', args: { settings: { language: 'Persian' } } })
    await bridge.saveSettings({}, { recover: true })
    expect(JSON.parse(invokeMock.mock.calls.at(-1)![1].request)).toEqual({ cmd: 'set-settings', args: { settings: {}, recover: true } })
    await bridge.retryResources()
    expect(JSON.parse(invokeMock.mock.calls.at(-1)![1].request)).toEqual({ cmd: 'retry-resources', args: {} })
  })

  it('restores the bubble after backend readiness and retries failed settings reads', async () => {
    vi.useFakeTimers()
    const settings = { ...(await createMockBridge().getSettings()), bubble_position: [1500, 80] as [number, number] }
    const getSettings = vi.fn().mockRejectedValueOnce(new Error('Not ready yet')).mockResolvedValue(settings)
    const bridge = { ...createMockBridge(), getSettings }
    const starting: BackendStatus = { status: 'starting', owned: true, message: '', log_path: '' }
    const ui = (status: BackendStatus) => <BridgeContext.Provider value={bridge}><BackendStatusContext.Provider value={context(status)}><TauriBubbleController /></BackendStatusContext.Provider></BridgeContext.Provider>
    const { rerender } = render(ui(starting))
    expect(getSettings).not.toHaveBeenCalled()
    rerender(ui({ ...starting, status: 'ready' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(invokeMock).not.toHaveBeenCalledWith('bubble_show', expect.anything())
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(invokeMock).toHaveBeenCalledExactlyOnceWith('bubble_show', { x: 1500, y: 80 })
  })

  it('debounces bubble moves into a position-only patch without reading settings', async () => {
    vi.useFakeTimers()
    let move!: (event: { payload: { x: number; y: number } }) => void
    movedMock.mockImplementation(async (callback) => { move = callback; return () => {} })
    const bridge = createMockBridge()
    const save = vi.spyOn(bridge, 'saveSettings')
    const read = vi.spyOn(bridge, 'getSettings')
    render(<BridgeContext.Provider value={bridge}><FloatingBubbleSurface /></BridgeContext.Provider>)
    await act(async () => { move({ payload: { x: 100, y: 200 } }); move({ payload: { x: 110, y: 220 } }); await vi.advanceTimersByTimeAsync(351) })
    expect(save).toHaveBeenCalledExactlyOnceWith({ bubble_position: [110, 220] })
    expect(read).not.toHaveBeenCalled()
  })

  it('refreshes persistent quick history when placement signals a new show', async () => {
    const getHistory = vi.fn().mockResolvedValueOnce([{ text: 'Old entry', created_at: null }]).mockResolvedValue([{ text: 'New entry', created_at: null }])
    render(<BridgeContext.Provider value={{ ...createMockBridge(), getHistory }}><QuickHistoryPopoverSurface /></BridgeContext.Provider>)
    expect(await screen.findByText('Old entry')).toBeInTheDocument()
    await act(async () => { handlers.get('local-dictation:popover-placement')!({ payload: { tail_x: 200 } }) })
    expect(await screen.findByText('New entry')).toBeInTheDocument()
    expect(screen.queryByText('Old entry')).not.toBeInTheDocument()
  })

  it('retains the newest bubble position after a busy settings rejection', async () => {
    vi.useFakeTimers()
    let move!: (event: { payload: { x: number; y: number } }) => void
    movedMock.mockImplementation(async (callback) => { move = callback; return () => {} })
    const bridge = createMockBridge()
    const save = vi.spyOn(bridge, 'saveSettings').mockRejectedValueOnce(new Error('Settings are busy'))
    render(<BridgeContext.Provider value={bridge}><FloatingBubbleSurface /></BridgeContext.Provider>)
    await act(async () => { move({ payload: { x: 100, y: 200 } }); await vi.advanceTimersByTimeAsync(351) })
    expect(save).toHaveBeenCalledTimes(1)
    await act(async () => { move({ payload: { x: 120, y: 230 } }); await vi.advanceTimersByTimeAsync(1400) })
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith({ bubble_position: [120, 230] })
  })

  it('retries an unchanged position without another move or recovery permission', async () => {
    vi.useFakeTimers()
    let move!: (event: { payload: { x: number; y: number } }) => void
    movedMock.mockImplementation(async (callback) => { move = callback; return () => {} })
    const bridge = createMockBridge()
    const save = vi.spyOn(bridge, 'saveSettings').mockRejectedValueOnce(new Error('Settings are busy'))
    render(<BridgeContext.Provider value={bridge}><FloatingBubbleSurface /></BridgeContext.Provider>)
    await act(async () => { move({ payload: { x: 100, y: 200 } }); await vi.advanceTimersByTimeAsync(1400) })
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith({ bubble_position: [100, 200] })
  })

  it('receives native appearance without re-emitting and composes a user edit with the current store', async () => {
    render(<ThemeProvider><AppearanceProbe /></ThemeProvider>)
    await act(async () => { await Promise.resolve() })
    localStorage.setItem('local-dictation-theme', JSON.stringify({ mode: 'dark', preset: 'blue' }))
    await act(async () => { handlers.get('local-dictation:appearance')!({ payload: { mode: 'system', preset: 'neutral' } }) })
    expect(screen.getByText('dark/blue')).toBeInTheDocument()
    expect(emitMock).not.toHaveBeenCalled()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Green' }))
    expect(JSON.parse(localStorage.getItem('local-dictation-theme')!)).toEqual({ mode: 'dark', preset: 'green' })
    expect(emitMock).toHaveBeenCalledExactlyOnceWith('local-dictation:appearance', { mode: 'dark', preset: 'green' })
  })
})
