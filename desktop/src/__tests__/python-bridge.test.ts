import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest'

import type { Settings } from '@/bridge/types'

const invokeMock = vi.hoisted(() => vi.fn())

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
  isTauri: () => false,
}))

import { createBridgeForRuntime, getBridgeRuntimeLabel } from '@/bridge'
import { createPythonBridge } from '@/bridge/pythonBridge'

const settingsResponse: Settings = {
  language: 'English (US)',
  model: 'Balanced',
  model_order: 'Speed',
  device_mode: 'auto',
  theme: 'Dark Mode',
  opacity: 96,
  text_format: 'Plain Text',
  save_location: '',
  hotkey: '<ctrl>+<alt>+d',
  bubble_position: [10, 20],
  custom_models: [],
}

function lastBridgeRequest() {
  const args = invokeMock.mock.calls.at(-1)?.[1] as { request: string }
  return JSON.parse(args.request) as { cmd: string; args: Record<string, unknown> }
}

describe('python bridge', () => {
  beforeEach(() => {
    invokeMock.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sends read requests through the Tauri bridge command', async () => {
    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: settingsResponse }))

    const bridge = createPythonBridge()
    await expect(bridge.getSettings()).resolves.toEqual(settingsResponse)

    expect(invokeMock).toHaveBeenCalledWith('bridge_call', { request: expect.any(String) })
    expect(lastBridgeRequest()).toEqual({ cmd: 'get-settings', args: {} })
  })

  it('maps model and state read responses into the shared bridge types', async () => {
    const bridge = createPythonBridge()

    invokeMock.mockResolvedValueOnce(
      JSON.stringify({
        ok: true,
        data: [
          {
            tier: 'High Accuracy',
            model_name: 'large-v3',
            repo_id: 'Systran/faster-whisper-large-v3',
            description: 'best quality, slower',
            cache_dir: 'C:\\dictation-test-profile\\.cache\\huggingface\\hub',
            available: true,
            revision: 'abc123',
            size_bytes: 1024,
            size_text: '1 KB',
            source_type: 'builtin',
            custom: false,
            speed_rank: 6,
            accuracy_rank: 1,
          },
        ],
      }),
    )

    await expect(bridge.getModels('Accuracy')).resolves.toMatchObject([{ tier: 'High Accuracy', accuracy_rank: 1 }])
    expect(lastBridgeRequest()).toEqual({ cmd: 'list-models', args: { order: 'Accuracy' } })

    invokeMock.mockResolvedValueOnce(
      JSON.stringify({
        ok: true,
        data: {
          recording: false,
          transcribing: false,
          waiting_for_target_click: true,
          status: 'paste-ready',
          latestTranscript: 'Ready text',
          activeModel: 'Balanced',
          activeLanguage: 'English (US)',
        },
      }),
    )

    await expect(bridge.getState()).resolves.toMatchObject({ status: 'paste-ready', latestTranscript: 'Ready text' })
    expect(lastBridgeRequest()).toEqual({ cmd: 'get-state', args: {} })
  })

  it('rejects bridge error responses and normalizes connection failures', async () => {
    const bridge = createPythonBridge()

    invokeMock.mockResolvedValueOnce(JSON.stringify({ ok: false, error: 'Unknown command: nope' }))
    await expect(bridge.getHistory()).rejects.toThrow('Unknown command: nope')

    invokeMock.mockResolvedValueOnce('error')
    await expect(bridge.getState()).rejects.toThrow('bridge protocol is incompatible')

    invokeMock.mockReset()
    invokeMock.mockRejectedValueOnce(new Error('Connection refused'))
    await expect(bridge.getState()).rejects.toThrow('Local Dictation is not running. Start or retry the backend in Help/About.')
  })

  it('sends write and action requests through the Tauri bridge command', async () => {
    const bridge = createPythonBridge()

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: settingsResponse }))
    await expect(bridge.saveSettings(settingsResponse)).resolves.toEqual(settingsResponse)
    expect(lastBridgeRequest()).toEqual({ cmd: 'set-settings', args: { settings: settingsResponse } })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: [] }))
    await expect(bridge.clearHistory()).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'clear-history', args: {} })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: 'C:\\out\\history.txt' }))
    await expect(bridge.exportHistory('txt')).resolves.toBe('C:\\out\\history.txt')
    expect(lastBridgeRequest()).toEqual({ cmd: 'export-history', args: { format: 'txt' } })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: { choice: 'Fast', status: 'downloading' } }))
    await expect(bridge.downloadModel('Fast')).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'download-model', args: { choice: 'Fast' } })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: 'C:\\models' }))
    await expect(bridge.openModelFolder('Fast')).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'open-model-folder', args: { choice: 'Fast' } })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: 'C:\\models' }))
    await expect(bridge.copyModelPath('Fast')).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'copy-model-path', args: { choice: 'Fast' } })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: settingsResponse }))
    await expect(bridge.addCustomModel('Custom', 'owner/model')).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'add-custom-model', args: { name: 'Custom', source: 'owner/model' } })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: { accepted: true } }))
    await expect(bridge.startRecording()).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'start-recording', args: {} })
    await expect(bridge.stopRecording()).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'stop-recording', args: {} })
    await expect(bridge.toggleRecording()).resolves.toBeUndefined()
    expect(lastBridgeRequest()).toEqual({ cmd: 'toggle-recording', args: {} })
  })

  it('polls state changes and unsubscribes cleanly', async () => {
    vi.useFakeTimers()
    const bridge = createPythonBridge()
    const listener = vi.fn()
    const idleState = {
      recording: false,
      transcribing: false,
      waiting_for_target_click: false,
      status: 'idle',
      latestTranscript: '',
      activeModel: 'Balanced',
      activeLanguage: 'English (US)',
    }
    const recordingState = { ...idleState, recording: true, status: 'recording' }

    invokeMock
      .mockResolvedValueOnce(JSON.stringify({ ok: true, data: idleState }))
      .mockResolvedValueOnce(JSON.stringify({ ok: true, data: recordingState }))

    const unsubscribe = bridge.onState(listener)
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(750)

    expect(listener).toHaveBeenCalledTimes(2)
    expect(listener).toHaveBeenLastCalledWith({ ...recordingState, connected: true, connection_error: undefined })

    unsubscribe()
    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: { ...recordingState, latestTranscript: 'new' } }))
    await vi.runOnlyPendingTimersAsync()
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('selects mock bridge in browser mode and python bridge in Tauri mode', async () => {
    expect(getBridgeRuntimeLabel(false)).toBe('Mock UI')
    expect(getBridgeRuntimeLabel(true)).toBe('Local bridge')

    await expect(createBridgeForRuntime(false).getSettings()).resolves.toMatchObject({ model: 'Balanced' })

    invokeMock.mockResolvedValue(JSON.stringify({ ok: true, data: settingsResponse }))
    await expect(createBridgeForRuntime(true).getSettings()).resolves.toEqual(settingsResponse)
    expect(lastBridgeRequest()).toEqual({ cmd: 'get-settings', args: {} })
  })

  it('calls Tauri backend lifecycle commands directly', async () => {
    const bridge = createPythonBridge()
    const backendStatus = {
      status: 'ready',
      owned: true,
      message: 'Local backend ready.',
      log_path: 'C:\\local-dictation\\dictation_debug.log',
      health: {
        version: '0.5.0-sidecar-ready',
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

    invokeMock
      .mockResolvedValueOnce(backendStatus)
      .mockResolvedValueOnce(backendStatus)
      .mockResolvedValueOnce(backendStatus.health)
      .mockResolvedValueOnce(backendStatus)
      .mockResolvedValueOnce(backendStatus)

    await expect(bridge.getBackendStatus()).resolves.toEqual(backendStatus)
    expect(invokeMock).toHaveBeenLastCalledWith('backend_status')

    await expect(bridge.startBackend()).resolves.toEqual(backendStatus)
    expect(invokeMock).toHaveBeenLastCalledWith('backend_start')

    await expect(bridge.getBackendHealth()).resolves.toEqual(backendStatus.health)
    expect(invokeMock).toHaveBeenLastCalledWith('backend_health')

    await expect(bridge.restartBackend()).resolves.toEqual(backendStatus)
    expect(invokeMock).toHaveBeenLastCalledWith('backend_restart')

    await expect(bridge.stopBackend()).resolves.toEqual(backendStatus)
    expect(invokeMock).toHaveBeenLastCalledWith('backend_stop')
  })
})
