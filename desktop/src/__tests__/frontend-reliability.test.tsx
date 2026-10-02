import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

import type { AppState, BackendStatus, Bridge } from '@/bridge/types'
import { BridgeContext } from '@/bridge/bridgeContext'
import { BackendStatusContext } from '@/bridge/BackendStatusContext'
import { createMockBridge } from '@/bridge/mockBridge'
import { SettingsPage } from '@/pages/SettingsPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { ModelsPage } from '@/pages/ModelsPage'
import { ExportsPage } from '@/pages/ExportsPage'
import { RecordingPage } from '@/pages/RecordingPage'
import { HotkeyInput } from '@/components/settings/HotkeyInput'
import { RecordButton } from '@/components/dictation/RecordButton'
import { HistoryRow } from '@/components/history/HistoryRow'
import { ThemeProvider, useTheme } from '@/theme/theme-provider'
import { defaultSettings } from '@/fixtures/settings'
import { modelFixtures } from '@/fixtures/models'

const idle: AppState = {
  recording: false, transcribing: false, waiting_for_target_click: false, status: 'idle',
  latestTranscript: '', activeModel: 'Balanced', activeLanguage: 'English (US)', history_revision: 0,
}

function renderPage(ui: React.ReactNode, bridge: Bridge) {
  return render(<BridgeContext.Provider value={bridge}><ThemeProvider>{ui}</ThemeProvider></BridgeContext.Provider>)
}

function ThemeProbe() {
  const { mode, preset } = useTheme()
  return <span>{mode}/{preset}</span>
}

describe('frontend reliability', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })
  afterEach(() => { vi.useRealTimers(); Object.defineProperty(document, 'hidden', { configurable: true, value: false }) })

  it('saves only edited settings and locks the form until the save completes', async () => {
    const user = userEvent.setup()
    let resolve!: (value: typeof defaultSettings) => void
    const saveSettings = vi.fn(() => new Promise<typeof defaultSettings>((done) => { resolve = done }))
    const bridge = { ...createMockBridge(), saveSettings }
    renderPage(<SettingsPage />, bridge)
    const location = await screen.findByLabelText('Save Location')
    await user.type(location, 'C:\\exports')
    const save = screen.getByRole('button', { name: /save changes/i })
    await user.dblClick(save)
    expect(saveSettings).toHaveBeenCalledExactlyOnceWith({ save_location: 'C:\\exports' }, { recover: true })
    expect(location).toBeDisabled()
    expect(save).toBeDisabled()
    await act(async () => { resolve({ ...defaultSettings, save_location: 'C:\\exports', bubble_position: [200, 300] }) })
    expect(location).toBeEnabled()
  })

  it('recovers a failed settings read through Retry and keeps native opacity out of the form', async () => {
    const bridge = { ...createMockBridge(), getSettings: vi.fn().mockRejectedValueOnce(new Error('Starting backend')).mockResolvedValue(defaultSettings) }
    const user = userEvent.setup()
    renderPage(<SettingsPage />, bridge)
    await user.click(await screen.findByRole('button', { name: /retry/i }))
    expect(await screen.findByLabelText('Input Language')).toBeInTheDocument()
    expect(screen.queryByText('Panel Opacity')).not.toBeInTheDocument()
  })

  it('offers explicit recovery of unreadable settings and history', async () => {
    const recoveryState = { ...idle, settings_error: 'Invalid settings JSON', history_error: 'Invalid history JSON' }
    const bridge = { ...createMockBridge(), getState: vi.fn(async () => recoveryState),
      onState: (listener: (state: AppState) => void) => { listener(recoveryState); return () => {} },
      getHistory: vi.fn(async () => []), clearHistory: vi.fn(async () => undefined),
      saveSettings: vi.fn(async () => defaultSettings) }
    renderPage(<><SettingsPage /><HistoryPage /></>, bridge)
    await screen.findByLabelText('Save Location')
    expect(await screen.findByText(/Invalid settings JSON/)).toBeInTheDocument()
    expect(screen.getByText(/Invalid history JSON/)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /save changes/i }))
    expect(bridge.saveSettings).toHaveBeenCalledExactlyOnceWith({}, { recover: true })
    const clear = screen.getByRole('button', { name: 'Clear' })
    expect(clear).toBeEnabled()
    await userEvent.setup().click(clear)
    expect(bridge.clearHistory).toHaveBeenCalledOnce()
  })

  it('does not let an older reconnect read overwrite a completed save', async () => {
    let notify!: (state: AppState) => void
    let resolveRead!: (value: typeof defaultSettings) => void
    const getSettings = vi.fn().mockResolvedValueOnce(defaultSettings)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveRead = resolve }))
    const bridge = { ...createMockBridge(), getSettings, getState: vi.fn(async () => idle),
      saveSettings: vi.fn(async () => ({ ...defaultSettings, save_location: 'new location' })),
      onState: (listener: (state: AppState) => void) => { notify = listener; return () => {} } }
    renderPage(<SettingsPage />, bridge)
    const input = await screen.findByLabelText('Save Location')
    await act(async () => { notify({ ...idle, connected: false }) })
    await act(async () => { notify({ ...idle, connected: true }) })
    expect(getSettings).toHaveBeenCalledTimes(2)
    await userEvent.setup().type(input, 'new location')
    await userEvent.setup().click(screen.getByRole('button', { name: /save changes/i }))
    await act(async () => { resolveRead(defaultSettings) })
    expect(input).toHaveValue('new location')
  })

  it.each([
    [' ', { ctrlKey: true }, '<ctrl>+<space>'],
    ['Enter', { ctrlKey: true }, '<ctrl>+<enter>'],
    ['d', { ctrlKey: true, shiftKey: true }, '<ctrl>+<shift>+d'],
    ['F8', { altKey: true }, '<alt>+<f8>'],
    ['ArrowUp', { metaKey: true }, '<cmd>+<up>'],
  ])('captures the supported shortcut %s', (key, modifiers, expected) => {
    const onChange = vi.fn()
    render(<HotkeyInput value="" onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('textbox'), { key, ...modifiers })
    expect(onChange).toHaveBeenCalledWith(expected)
  })

  it('leaves the hotkey field with Tab and Shift+Tab', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<><button>Before</button><HotkeyInput value="<ctrl>+d" onChange={onChange} /><button>After</button></>)
    screen.getByRole('textbox').focus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('textbox')).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Before' })).toHaveFocus()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('refreshes an open history page for repeated identical transcripts', async () => {
    let notify!: (state: AppState) => void
    const getHistory = vi.fn().mockResolvedValueOnce([{ text: 'old', created_at: null }]).mockResolvedValue([{ text: 'same text', created_at: null }])
    const bridge = { ...createMockBridge(), getState: vi.fn(async () => idle), getHistory,
      onState: (listener: (state: AppState) => void) => { notify = listener; return () => {} } }
    renderPage(<HistoryPage />, bridge)
    expect(await screen.findByText('old')).toBeInTheDocument()
    await act(async () => { notify({ ...idle, latestTranscript: 'same text', history_revision: 1 }) })
    expect(await screen.findByText('same text')).toBeInTheDocument()
    await act(async () => { notify({ ...idle, latestTranscript: 'same text', history_revision: 2 }) })
    expect(getHistory).toHaveBeenCalledTimes(3)
  })

  it('keeps model cards during a transient download poll failure and continues polling', async () => {
    vi.useFakeTimers()
    const downloading = { ...modelFixtures[0], available: false, download_status: 'downloading' as const }
    const installed = { ...downloading, available: true, download_status: 'installed' as const }
    const getModels = vi.fn().mockResolvedValueOnce([downloading]).mockRejectedValueOnce(new Error('Temporary disconnect')).mockResolvedValue([installed])
    renderPage(<ModelsPage />, { ...createMockBridge(), getModels })
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(screen.getByRole('button', { name: /downloading/i })).toBeDisabled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1600) })
    expect(screen.getByRole('button', { name: /downloading/i })).toBeDisabled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1600) })
    expect(screen.getByRole('button', { name: /installed/i })).toBeDisabled()
  })

  it('pauses model download polling while hidden and refreshes immediately on show', async () => {
    vi.useFakeTimers()
    const downloading = { ...modelFixtures[0], available: false, download_status: 'downloading' as const }
    const getModels = vi.fn().mockResolvedValue([downloading])
    renderPage(<ModelsPage />, { ...createMockBridge(), getModels })
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(getModels).toHaveBeenCalledOnce()
    await act(async () => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true })
      document.dispatchEvent(new Event('visibilitychange'))
      await vi.advanceTimersByTimeAsync(3000)
    })
    expect(getModels).toHaveBeenCalledOnce()
    await act(async () => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: false })
      document.dispatchEvent(new Event('visibilitychange'))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(getModels).toHaveBeenCalledTimes(2)
  })

  it('disables Start while transcription or resource loading is active', () => {
    const { rerender } = render(<RecordButton state={{ ...idle, transcribing: true, status: 'transcribing' }} onToggle={vi.fn()} />)
    expect(screen.getByRole('button', { name: /start recording/i })).toBeDisabled()
    rerender(<RecordButton state={{ ...idle, loading: true }} onToggle={vi.fn()} />)
    expect(screen.getByRole('button', { name: /start recording/i })).toBeDisabled()
  })

  it('retains a completed transcript when backend health becomes unavailable', async () => {
    const bridge = { ...createMockBridge(), getState: vi.fn(async () => ({ ...idle, latestTranscript: 'Keep this completed text' })), onState: () => () => {} }
    const ui = (status: BackendStatus) => <BridgeContext.Provider value={bridge}><ThemeProvider><BackendStatusContext.Provider value={{ backendStatus: status, refreshBackendStatus: async () => status, startBackend: async () => status, stopBackend: async () => status, restartBackend: async () => status }}><RecordingPage /></BackendStatusContext.Provider></ThemeProvider></BridgeContext.Provider>
    const { rerender } = render(ui({ status: 'ready', owned: true, message: 'Ready', log_path: '' }))
    expect(await screen.findByText('Keep this completed text')).toBeInTheDocument()
    rerender(ui({ status: 'unhealthy', owned: true, message: 'Backend disconnected', log_path: '' }))
    expect(screen.getByText('Keep this completed text')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start recording/i })).toBeDisabled()
  })

  it('reports clipboard rejection without announcing copy success', async () => {
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Clipboard is busy'))
    const success = vi.spyOn(toast, 'success')
    const error = vi.spyOn(toast, 'error')
    const user = userEvent.setup()
    render(<HistoryRow entry={{ text: 'retained text', created_at: null }} />)
    await user.click(screen.getByRole('button', { name: /copy transcript/i }))
    await waitFor(() => expect(error).toHaveBeenCalledWith('Clipboard is busy'))
    expect(success).not.toHaveBeenCalled()
    expect(screen.getByText('retained text')).toBeInTheDocument()
  })

  it('applies storage appearance changes without rewriting the received preference', async () => {
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
    const incoming = JSON.stringify({ mode: 'dark', preset: 'blue' })
    localStorage.setItem('local-dictation-theme', incoming)
    const write = vi.spyOn(Storage.prototype, 'setItem')
    act(() => { window.dispatchEvent(new StorageEvent('storage', { key: 'local-dictation-theme', newValue: incoming })) })
    expect(await screen.findByText('dark/blue')).toBeInTheDocument()
    expect(document.documentElement).toHaveClass('dark', 'theme-blue')
    expect(write).not.toHaveBeenCalled()
  })

  it('keeps the latest model order when a previous read completes late', async () => {
    let finishSpeed!: (models: typeof modelFixtures) => void
    const getModels = vi.fn().mockImplementationOnce(() => new Promise<typeof modelFixtures>((resolve) => { finishSpeed = resolve })).mockResolvedValue([modelFixtures[5]])
    renderPage(<ModelsPage />, { ...createMockBridge(), getModels })
    await userEvent.setup().click(screen.getByRole('button', { name: /accuracy order/i }))
    expect(await screen.findByText('High Accuracy (2.88 GB)')).toBeInTheDocument()
    await act(async () => { finishSpeed([modelFixtures[0]]) })
    expect(screen.getByText('High Accuracy (2.88 GB)')).toBeInTheDocument()
    expect(screen.queryByText('Ultra Fast English (79 MB)')).not.toBeInTheDocument()
  })

  it('keeps a folder on picker cancel and saves a selected path as a patch', async () => {
    const bridge = createMockBridge()
    const picker = vi.spyOn(bridge, 'pickExportFolder').mockResolvedValueOnce(null).mockResolvedValueOnce('C:\\selected')
    const save = vi.spyOn(bridge, 'saveSettings')
    const user = userEvent.setup()
    renderPage(<SettingsPage />, bridge)
    const input = await screen.findByLabelText('Save Location')
    await user.click(screen.getByRole('button', { name: 'Browse' }))
    expect(input).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Browse' }))
    expect(input).toHaveValue('C:\\selected')
    await user.click(screen.getByRole('button', { name: /save changes/i }))
    expect(picker).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenCalledExactlyOnceWith({ save_location: 'C:\\selected' }, { recover: true })
  })

  it('shows no fabricated export catalog and displays the actual export result', async () => {
    const bridge = { ...createMockBridge(), exportHistory: vi.fn(async () => 'C:\\exports\\actual.txt') }
    renderPage(<ExportsPage />, bridge)
    expect(screen.queryByRole('button', { name: /open folder|copy path/i })).not.toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Export all TXT' }))
    expect(await screen.findByRole('status')).toHaveTextContent('C:\\exports\\actual.txt')
    expect(bridge.exportHistory).toHaveBeenCalledExactlyOnceWith('txt')
  })
})
