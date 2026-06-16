import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { Toaster } from 'sonner'
import { describe, expect, it, vi } from 'vitest'

import type { AppState, BackendStatus, Bridge, HistoryEntry, ModelInfo, Settings, UpdateCheck } from '@/bridge/types'
import { BridgeContext } from '@/bridge/bridgeContext'
import { HistoryPage } from '@/pages/HistoryPage'
import { HelpAboutPage } from '@/pages/HelpAboutPage'
import { ModelsPage } from '@/pages/ModelsPage'
import { RecordingPage } from '@/pages/RecordingPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { ThemeProvider } from '@/theme/theme-provider'

const defaultSettings: Settings = {
  language: 'English (US)',
  model: 'Balanced',
  model_order: 'Speed',
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

const readyBackend: BackendStatus = {
  status: 'ready',
  owned: false,
  message: 'Mock UI backend simulated.',
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
    stopBackend: vi.fn(async () => readyBackend),
    restartBackend: vi.fn(async () => readyBackend),
    getBackendHealth: vi.fn(async () => readyBackend.health!),
    ...overrides,
  }
}

function renderWithBridge(ui: ReactNode, bridge: Bridge) {
  return render(
    <BridgeContext.Provider value={bridge}>
      <ThemeProvider>
        {ui}
        <Toaster richColors closeButton position="bottom-right" />
      </ThemeProvider>
    </BridgeContext.Provider>,
  )
}

describe('stage 3 UI behavior', () => {
  it('shows a recording control error when the local bridge rejects toggle', async () => {
    const user = userEvent.setup()
    const bridge = createTestBridge({
      toggleRecording: vi.fn(async () => {
        throw new Error('Local Dictation is not running.')
      }),
    })

    renderWithBridge(<RecordingPage />, bridge)

    await user.click(await screen.findByRole('button', { name: /start recording/i }))

    expect(await screen.findByText(/Local Dictation is not running/i)).toBeInTheDocument()
  })

  it('uses the exported file path in history export success copy', async () => {
    const user = userEvent.setup()
    const bridge = createTestBridge({
      getHistory: vi.fn(async (): Promise<HistoryEntry[]> => [{ text: 'hello', created_at: '2026-06-16T10:35:00' }]),
      exportHistory: vi.fn(async () => 'C:\\exports\\history.txt'),
    })

    renderWithBridge(<HistoryPage />, bridge)

    await user.click(screen.getByRole('button', { name: /export txt/i }))

    expect(await screen.findByText(/Exported to C:\\exports\\history.txt/i)).toBeInTheDocument()
  })

  it('disables a model download button while the model is downloading', async () => {
    const downloadingModel: ModelInfo = {
      tier: 'Fast',
      model_name: 'small',
      repo_id: 'Systran/faster-whisper-small',
      description: 'lowest latency',
      cache_dir: 'C:\\models',
      available: false,
      revision: '',
      size_bytes: 0,
      size_text: 'not installed locally',
      source_type: 'builtin',
      custom: false,
      speed_rank: 1,
      accuracy_rank: 4,
      download_status: 'downloading',
      download_error: '',
    }
    const bridge = createTestBridge({
      getModels: vi.fn(async () => [downloadingModel]),
    })

    renderWithBridge(<ModelsPage />, bridge)

    const downloadButton = await screen.findByRole('button', { name: /downloading/i })
    expect(downloadButton).toBeDisabled()
  })

  it('shows settings save failures without replacing the form', async () => {
    const user = userEvent.setup()
    const bridge = createTestBridge({
      saveSettings: vi.fn(async () => {
        throw new Error('Model is not installed locally: Fast')
      }),
    })

    renderWithBridge(<SettingsPage />, bridge)

    await user.click(await screen.findByRole('button', { name: /save changes/i }))

    expect(await screen.findByText(/Model is not installed locally: Fast/i)).toBeInTheDocument()
    expect(screen.getByText('Balanced')).toBeInTheDocument()
  })

  it('describes Stage 4 backend controls in Help/About', async () => {
    renderWithBridge(<HelpAboutPage />, createTestBridge())

    expect(await screen.findByText(/Stage 4 can start and monitor the local Python backend/i)).toBeInTheDocument()
    expect(screen.getByText(/Real backend start\/stop controls require the Tauri runtime/i)).toBeInTheDocument()
  })
})
