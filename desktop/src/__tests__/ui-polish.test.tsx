import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { AppState, BackendStatus, Bridge, Settings, UpdateCheck } from '@/bridge/types'
import { BridgeContext } from '@/bridge/bridgeContext'
import { HotkeyInput } from '@/components/settings/HotkeyInput'
import { ModelCard } from '@/components/models/ModelCard'
import { QuickHistoryPopoverPreview } from '@/components/dictation/QuickHistoryPopoverPreview'
import { StatusPill } from '@/components/shell/StatusPill'
import { SettingsPage } from '@/pages/SettingsPage'
import { modelFixtures } from '@/fixtures/models'
import { ThemeProvider } from '@/theme/theme-provider'

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

const readyBackend: BackendStatus = {
  status: 'ready',
  owned: false,
  message: 'Mock backend.',
  log_path: 'C:\\local-dictation\\dictation_debug.log',
}

function createBridge(overrides: Partial<Bridge> = {}): Bridge {
  return {
    getSettings: vi.fn(async () => defaultSettings),
    saveSettings: vi.fn(async () => defaultSettings),
    getHistory: vi.fn(async () => []),
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
    getBackendStatus: vi.fn(async () => readyBackend),
    startBackend: vi.fn(async () => readyBackend),
    stopBackend: vi.fn(async () => readyBackend),
    restartBackend: vi.fn(async () => readyBackend),
    getBackendHealth: vi.fn(async () => {
      throw new Error('No backend health in this test.')
    }),
    ...overrides,
  }
}

function renderWithBridge(ui: React.ReactNode, bridge = createBridge()) {
  return render(
    <BridgeContext.Provider value={bridge}>
      <ThemeProvider>{ui}</ThemeProvider>
    </BridgeContext.Provider>,
  )
}

describe('UI polish fixes', () => {
  it('renders idle status with readable secondary text', async () => {
    renderWithBridge(<StatusPill />)

    const idle = await screen.findByText('Idle')

    expect(idle).toHaveClass('text-secondary-foreground')
    expect(idle).not.toHaveClass('text-primary-foreground')
  })

  it('renders installed model status with readable green text and keeps download disabled', () => {
    const model = {
      ...modelFixtures[1],
      available: true,
      download_status: 'installed' as const,
    }

    render(<ModelCard model={model} onDownload={vi.fn()} onCopyPath={vi.fn()} onOpenFolder={vi.fn()} />)

    const installedBadge = screen.getAllByText('Installed')[0]
    expect(installedBadge).toHaveClass('text-emerald-700')
    expect(screen.getByRole('button', { name: /installed/i })).toBeDisabled()
  })

  it('shows aligned model sizes in Settings model select without changing model values', async () => {
    const user = userEvent.setup()
    const bridge = createBridge()
    renderWithBridge(<SettingsPage />, bridge)

    const modelTrigger = await screen.findByLabelText('Model')
    expect(modelTrigger).toHaveTextContent('Balanced')
    expect(modelTrigger).toHaveTextContent('(1.62 GB)')

    await user.click(modelTrigger)
    const ultraFastSize = await screen.findByText('(79 MB)')
    expect(ultraFastSize).toHaveClass('text-right')

    const fastOption = (await screen.findByText('Fast')).closest('[role="option"]')
    expect(fastOption).not.toBeNull()
    await user.click(fastOption!)
    await user.click(screen.getByRole('button', { name: /save changes/i }))

    expect(bridge.saveSettings).toHaveBeenCalledWith(expect.objectContaining({ model: 'Fast' }))
  })

  it('captures modifiers in hotkey input and replaces existing text', () => {
    const onChange = vi.fn()
    render(<HotkeyInput value="<ctrl>+<alt>+d" onChange={onChange} />)
    const input = screen.getByRole('textbox')

    fireEvent.keyDown(input, { key: 'd', code: 'KeyD', ctrlKey: true, altKey: true })
    fireEvent.keyDown(input, { key: 'g', code: 'KeyG', ctrlKey: true, shiftKey: true })
    fireEvent.keyDown(input, { key: 'a', code: 'KeyA' })
    fireEvent.keyDown(input, { key: 'Backspace', code: 'Backspace' })

    expect(onChange).toHaveBeenNthCalledWith(1, '<ctrl>+<alt>+d')
    expect(onChange).toHaveBeenNthCalledWith(2, '<ctrl>+<shift>+g')
    expect(onChange).toHaveBeenNthCalledWith(3, 'a')
    expect(onChange).toHaveBeenNthCalledWith(4, '')
  })

  it('uses the four-action footer in the floating transcript popover preview', () => {
    render(
      <QuickHistoryPopoverPreview
        entries={[
          {
            text: 'Even though this is a longer transcript preview.',
            created_at: '2026-06-16T11:39:00',
          },
        ]}
      />,
    )

    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /history/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tray/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^close$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /close app/i })).not.toBeInTheDocument()
  })
})
