import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { Toaster } from 'sonner'
import { describe, expect, it, vi } from 'vitest'

import type { AppState, BackendStatus, Bridge, Settings, UpdateCheck } from '@/bridge/types'
import { BackendStatusProvider } from '@/bridge/BackendStatusProvider'
import { BridgeContext } from '@/bridge/bridgeContext'
import { HelpAboutPage } from '@/pages/HelpAboutPage'
import { RecordingPage } from '@/pages/RecordingPage'
import { TopBar } from '@/components/shell/TopBar'
import { ThemeProvider } from '@/theme/theme-provider'

const defaultSettings: Settings = {
  language: 'English (US)',
  model: 'Balanced',
  model_order: 'Speed',
  device_mode: 'auto',
  theme: 'Dark Mode',
  opacity: 96,
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

const notRunningBackend: BackendStatus = {
  status: 'not_running',
  owned: false,
  message: 'Backend not running.',
  log_path: 'C:\\local-dictation\\dictation_debug.log',
}

const readyBackend: BackendStatus = {
  status: 'ready',
  owned: true,
  message: 'Local backend ready.',
  log_path: 'C:\\local-dictation\\dictation_debug.log',
  health: {
    version: '0.4.0-backend-manager',
    pid: 1234,
    status: 'idle',
    protocol_version: 4,
    backend_owner: 'api',
    model: 'Balanced',
    language: 'English (US)',
    device: 'cuda',
    uptime_seconds: 12,
  },
}

const browserMockBackend: BackendStatus = {
  status: 'ready',
  owned: false,
  message: 'Mock UI backend simulated. Tauri runtime is required to start Python.',
  log_path: 'C:\\local-dictation\\dictation_debug.log',
  health: {
    version: '0.4.0-browser-mock',
    pid: 0,
    status: 'idle',
    protocol_version: 4,
    backend_owner: 'browser-mock',
    model: 'Balanced',
    language: 'English (US)',
    device: 'mock',
    uptime_seconds: 0,
  },
}

function createTestBridge(overrides: Partial<Bridge> = {}): Bridge {
  return {
    getSettings: vi.fn(async () => defaultSettings),
    saveSettings: vi.fn(async () => undefined),
    getHistory: vi.fn(async () => []),
    clearHistory: vi.fn(async () => undefined),
    exportHistory: vi.fn(async () => 'C:\\exports\\history.txt'),
    getModels: vi.fn(async () => []),
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
    getBackendStatus: vi.fn(async () => readyBackend),
    startBackend: vi.fn(async () => readyBackend),
    stopBackend: vi.fn(async () => notRunningBackend),
    restartBackend: vi.fn(async () => readyBackend),
    getBackendHealth: vi.fn(async () => readyBackend.health!),
    ...overrides,
  }
}

function renderWithBridge(ui: ReactNode, bridge: Bridge) {
  return render(
    <BridgeContext.Provider value={bridge}>
      <ThemeProvider>
        <BackendStatusProvider autoStartInTauri={false}>{ui}</BackendStatusProvider>
        <Toaster richColors closeButton position="bottom-right" />
      </ThemeProvider>
    </BridgeContext.Provider>,
  )
}

describe('stage 4 backend lifecycle UI', () => {
  it('renders backend status in the top bar', async () => {
    renderWithBridge(<TopBar title="Recording" />, createTestBridge({ getBackendStatus: vi.fn(async () => readyBackend) }))

    expect(await screen.findByText('Local backend ready')).toBeInTheDocument()
  })

  it('labels browser mode as a mock backend instead of a local backend', async () => {
    renderWithBridge(<TopBar title="Recording" />, createTestBridge({ getBackendStatus: vi.fn(async () => browserMockBackend) }))

    expect(await screen.findByText('Mock backend')).toBeInTheDocument()
    expect(screen.queryByText('Local backend ready')).not.toBeInTheDocument()
  })

  it('disables recording when the local backend is unavailable', async () => {
    renderWithBridge(<RecordingPage />, createTestBridge({ getBackendStatus: vi.fn(async () => notRunningBackend) }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Backend not running/i)
    expect(await screen.findByRole('button', { name: /start recording/i })).toBeDisabled()
  })

  it('starts, restarts, and stops the backend from Help/About', async () => {
    const user = userEvent.setup()
    const bridge = createTestBridge({ getBackendStatus: vi.fn(async () => notRunningBackend) })

    renderWithBridge(<HelpAboutPage />, bridge)

    await user.click(await screen.findByRole('button', { name: /^Start backend$/i }))
    expect(bridge.startBackend).toHaveBeenCalledOnce()
    expect(await screen.findByText('Local backend ready.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Restart backend$/i }))
    expect(bridge.restartBackend).toHaveBeenCalledOnce()

    await user.click(screen.getByRole('button', { name: /^Stop backend$/i }))
    expect(bridge.stopBackend).toHaveBeenCalledOnce()
    expect(await screen.findByText('Backend not running.')).toBeInTheDocument()
  })

  it('disables backend process controls for browser mock mode', async () => {
    renderWithBridge(<HelpAboutPage />, createTestBridge({ getBackendStatus: vi.fn(async () => browserMockBackend) }))

    expect(await screen.findByRole('button', { name: /^Start backend$/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^Restart backend$/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^Stop backend$/i })).toBeDisabled()
    expect(screen.getByText(/Backend process controls require the Tauri runtime/i)).toBeInTheDocument()
  })
})
