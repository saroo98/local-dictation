import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { BackendStatusProvider } from '@/bridge/BackendStatusProvider'
import { BridgeContext } from '@/bridge/bridgeContext'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import type { AppState, BackendStatus, Bridge, Settings, UpdateCheck } from '@/bridge/types'
import { FloatingBubbleSurface } from '@/components/dictation/FloatingBubbleSurface'
import { QuickHistoryPopoverSurface } from '@/components/dictation/QuickHistoryPopoverSurface'
import { ModelCard } from '@/components/models/ModelCard'
import { StatusPill } from '@/components/shell/StatusPill'
import { RecordingPage } from '@/pages/RecordingPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { modelFixtures } from '@/fixtures/models'
import { ThemeProvider } from '@/theme/theme-provider'

const invokeMock = vi.hoisted(() => vi.fn())
const startDraggingMock = vi.hoisted(() => vi.fn(async () => undefined))
const onMovedMock = vi.hoisted(() => vi.fn(async () => () => {}))
const listenMock = vi.hoisted(() => vi.fn(async () => () => {}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
  isTauri: () => true,
}))

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({
    startDragging: startDraggingMock,
    onMoved: onMovedMock,
  }),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: listenMock,
}))

const defaultSettings: Settings = {
  language: 'English (US)',
  model: 'Balanced',
  model_order: 'Speed',
  device_mode: 'auto',
  theme: 'Dark Mode',
  opacity: 100,
  text_format: 'Plain Text',
  save_location: '',
  hotkey: '<ctrl>+<alt>+d',
  bubble_position: null,
  custom_models: [],
}

const idleState: AppState = {
  recording: false,
  transcribing: false,
  waiting_for_target_click: false,
  status: 'idle',
  latestTranscript: '',
  activeModel: 'Balanced',
  activeLanguage: 'English (US)',
}

const notRunning: BackendStatus = {
  status: 'not_running',
  owned: false,
  message: 'Backend not running.',
  log_path: 'C:\\local-dictation\\dictation_debug.log',
}

const starting: BackendStatus = {
  status: 'starting',
  owned: true,
  message: 'Backend starting. The speech model may still be loading.',
  log_path: 'C:\\local-dictation\\dictation_debug.log',
  launch_kind: 'python-fallback',
  starting_seconds: 1,
}

function createBridge(overrides: Partial<Bridge> = {}): Bridge {
  return {
    getSettings: vi.fn(async () => defaultSettings),
    saveSettings: vi.fn(async (settings) => settings),
    getHistory: vi.fn(async () => [{ text: 'Recent transcript', created_at: '2026-06-16T11:39:00' }]),
    clearHistory: vi.fn(async () => undefined),
    exportHistory: vi.fn(async () => 'C:\\exports\\history.txt'),
    getModels: vi.fn(async () => modelFixtures),
    downloadModel: vi.fn(async () => undefined),
    openModelFolder: vi.fn(async () => undefined),
    copyModelPath: vi.fn(async () => undefined),
    addCustomModel: vi.fn(async () => undefined),
    getState: vi.fn(async () => idleState),
    onState: vi.fn(() => () => {}),
    startRecording: vi.fn(async () => undefined),
    stopRecording: vi.fn(async () => undefined),
    toggleRecording: vi.fn(async () => undefined),
    checkForUpdates: vi.fn(async (): Promise<UpdateCheck> => ({ current: 'test' })),
    getBackendStatus: vi.fn(async () => notRunning),
    startBackend: vi.fn(async () => starting),
    stopBackend: vi.fn(async () => notRunning),
    restartBackend: vi.fn(async () => starting),
    getBackendHealth: vi.fn(async () => {
      throw new Error('No health in this test.')
    }),
    ...overrides,
  }
}

function renderWithBridge(ui: ReactNode, bridge = createBridge()) {
  return render(
    <BridgeContext.Provider value={bridge}>
      <ThemeProvider>{ui}</ThemeProvider>
    </BridgeContext.Provider>,
  )
}

function renderWithBackendProvider(ui: ReactNode, bridge = createBridge()) {
  return render(
    <BridgeContext.Provider value={bridge}>
      <ThemeProvider>
        <BackendStatusProvider autoStartInTauri>{ui}</BackendStatusProvider>
      </ThemeProvider>
    </BridgeContext.Provider>,
  )
}

function BackendProbe() {
  const { backendStatus } = useBackendStatus()
  return <div>{backendStatus?.status ?? 'checking'}</div>
}

describe('stage 6 device and Tauri surfaces', () => {
  it('auto-starts the backend once through the shared provider when Tauri owns the app', async () => {
    const bridge = createBridge()

    renderWithBackendProvider(<BackendProbe />, bridge)

    await waitFor(() => expect(bridge.startBackend).toHaveBeenCalledOnce())
    expect(await screen.findByText('starting')).toBeInTheDocument()
  })

  it('renders device choices including disabled Vulkan and saves the stored device value', async () => {
    const user = userEvent.setup()
    const bridge = createBridge()
    renderWithBridge(<SettingsPage />, bridge)

    await user.click(await screen.findByLabelText('Device'))
    expect(await screen.findByRole('option', { name: /Vulkan/i })).toHaveAttribute('aria-disabled', 'true')
    await user.click(screen.getByRole('option', { name: /^CPU only$/i }))
    await user.click(screen.getByRole('button', { name: /save changes/i }))

    expect(bridge.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ device_mode: 'cpu' }))
  })

  it('shows model card names with size in parentheses', () => {
    render(<ModelCard model={modelFixtures[1]} onDownload={vi.fn()} onCopyPath={vi.fn()} onOpenFolder={vi.fn()} />)

    expect(screen.getByText('Fast (464 MB)')).toBeInTheDocument()
  })

  it('Tauri bubble left-click toggles recording and right-click opens the React popover window', async () => {
    const user = userEvent.setup()
    const bridge = createBridge()
    renderWithBridge(<FloatingBubbleSurface />, bridge)

    await user.click(await screen.findByRole('button', { name: /toggle recording/i }))
    expect(bridge.toggleRecording).toHaveBeenCalledOnce()

    await user.pointer({ keys: '[MouseRight]', target: screen.getByRole('button', { name: /toggle recording/i }) })
    expect(invokeMock).toHaveBeenCalledWith('quick_popover_show')
  })

  it('Tauri bubble drag uses native window dragging instead of toggling recording', async () => {
    const bridge = createBridge()
    renderWithBridge(<FloatingBubbleSurface />, bridge)

    const bubble = await screen.findByRole('button', { name: /toggle recording/i })
    fireEvent.pointerDown(bubble, { button: 0, buttons: 1, clientX: 10, clientY: 10 })
    fireEvent.pointerMove(bubble, { buttons: 1, clientX: 24, clientY: 24 })
    fireEvent.click(bubble)

    await waitFor(() => expect(startDraggingMock).toHaveBeenCalledOnce())
    expect(bridge.toggleRecording).not.toHaveBeenCalled()
  })

  it('React quick popover uses real history and four footer actions', async () => {
    renderWithBridge(<QuickHistoryPopoverSurface />)

    expect(await screen.findByText('Recent transcript')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /history/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tray/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^close$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /close app/i })).not.toBeInTheDocument()
  })

  it('React quick popover tray hides the app and close hides only the popover', async () => {
    const user = userEvent.setup()
    renderWithBridge(<QuickHistoryPopoverSurface />)

    await user.click(await screen.findByRole('button', { name: /tray/i }))
    expect(invokeMock).toHaveBeenCalledWith('app_hide_to_tray')

    await user.click(screen.getByRole('button', { name: /^close$/i }))
    expect(invokeMock).toHaveBeenCalledWith('quick_popover_hide')
    expect(invokeMock).not.toHaveBeenCalledWith('app_quit')
  })

  it('status pill shows backend startup instead of recording error while backend is starting', async () => {
    const bridge = createBridge({
      getBackendStatus: vi.fn(async () => starting),
      getState: vi.fn(async () => {
        throw new Error('get-state should not be called while starting')
      }),
    })

    renderWithBackendProvider(<StatusPill />, bridge)

    expect(await screen.findByText('Starting')).toBeInTheDocument()
    expect(screen.queryByText('Error')).not.toBeInTheDocument()
    expect(bridge.getState).not.toHaveBeenCalled()
  })

  it('Recording page treats backend startup as starting and does not request app state yet', async () => {
    const bridge = createBridge({
      getBackendStatus: vi.fn(async () => starting),
      getState: vi.fn(async () => {
        throw new Error('get-state should not be called while backend is starting')
      }),
      getHistory: vi.fn(async () => []),
      onState: vi.fn(() => () => {}),
    })

    renderWithBackendProvider(<RecordingPage />, bridge)

    expect(await screen.findByText('Backend starting')).toBeInTheDocument()
    expect(screen.queryByText('Backend not running')).not.toBeInTheDocument()
    expect(bridge.getState).not.toHaveBeenCalled()
  })
})
