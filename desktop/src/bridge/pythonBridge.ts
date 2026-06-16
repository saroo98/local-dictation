import { invoke } from '@tauri-apps/api/core'

import type {
  AppState,
  BackendHealth,
  BackendStartResult,
  BackendStatus,
  BackendStopResult,
  Bridge,
  HistoryEntry,
  ModelInfo,
  ModelOrder,
  Settings,
  UpdateCheck,
} from '@/bridge/types'

interface BridgeResponse<T> {
  ok: boolean
  data?: T
  error?: string
}

const localBridgeUnavailableMessage = 'Local Dictation is not running. Start the Python app first.'
const incompatibleLocalBridgeMessage =
  'Local Dictation is running, but it does not support the Stage 4 JSON bridge. Close the old Python app, then start the backend from this Tauri build.'

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function normalizeInvokeError(error: unknown): Error {
  const message = errorMessage(error)
  const lower = message.toLowerCase()
  if (
    lower.includes('connection refused') ||
    lower.includes('actively refused') ||
    lower.includes('failed to connect') ||
    lower.includes('timed out') ||
    lower.includes('os error 10061')
  ) {
    return new Error(localBridgeUnavailableMessage)
  }
  return new Error(message)
}

async function callPython<T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> {
  let responseText: string
  try {
    responseText = await invoke<string>('bridge_call', {
      request: JSON.stringify({ cmd, args }),
    })
  } catch (error) {
    throw normalizeInvokeError(error)
  }

  let response: BridgeResponse<T>
  try {
    response = JSON.parse(responseText) as BridgeResponse<T>
  } catch {
    const trimmed = responseText.trim().toLowerCase()
    if (trimmed === 'ok' || trimmed === 'error') {
      throw new Error(incompatibleLocalBridgeMessage)
    }
    throw new Error('Local bridge returned invalid JSON.')
  }

  if (!response.ok) {
    throw new Error(response.error || 'Local bridge request failed.')
  }

  return response.data as T
}

async function callTauri<T>(command: string): Promise<T> {
  try {
    return await invoke<T>(command)
  } catch (error) {
    throw normalizeInvokeError(error)
  }
}

export function createPythonBridge(): Bridge {
  return {
    getSettings() {
      return callPython<Settings>('get-settings')
    },
    saveSettings(settings) {
      return callPython<Settings>('set-settings', { settings })
    },
    getHistory() {
      return callPython<HistoryEntry[]>('get-history')
    },
    clearHistory() {
      return callPython<HistoryEntry[]>('clear-history').then(() => undefined)
    },
    exportHistory(format) {
      return callPython<string>('export-history', { format })
    },
    getModels(order: ModelOrder) {
      return callPython<ModelInfo[]>('list-models', { order })
    },
    downloadModel(choice) {
      return callPython<{ choice: string; status: string }>('download-model', { choice }).then(() => undefined)
    },
    openModelFolder(choice) {
      return callPython<string>('open-model-folder', { choice }).then(() => undefined)
    },
    copyModelPath(choice) {
      return callPython<string>('copy-model-path', { choice }).then(() => undefined)
    },
    addCustomModel(name, source) {
      return callPython<Settings>('add-custom-model', { name, source }).then(() => undefined)
    },
    getState() {
      return callPython<AppState>('get-state')
    },
    onState(callback) {
      let disposed = false
      let previous = ''

      async function poll() {
        try {
          const state = await callPython<AppState>('get-state')
          if (disposed) return
          const serialized = JSON.stringify(state)
          if (serialized !== previous) {
            previous = serialized
            callback(state)
          }
        } catch {
          // Polling should not surface repeated background errors; direct actions still throw.
        }
      }

      const interval = window.setInterval(() => {
        void poll()
      }, 750)

      return () => {
        disposed = true
        window.clearInterval(interval)
      }
    },
    startRecording() {
      return callPython<{ accepted: boolean }>('start-recording').then(() => undefined)
    },
    stopRecording() {
      return callPython<{ accepted: boolean }>('stop-recording').then(() => undefined)
    },
    toggleRecording() {
      return callPython<{ accepted: boolean }>('toggle-recording').then(() => undefined)
    },
    checkForUpdates(): Promise<UpdateCheck> {
      return Promise.reject(new Error('Update checks are not available in Stage 3.'))
    },
    getBackendStatus() {
      return callTauri<BackendStatus>('backend_status')
    },
    startBackend() {
      return callTauri<BackendStartResult>('backend_start')
    },
    stopBackend() {
      return callTauri<BackendStopResult>('backend_stop')
    },
    restartBackend() {
      return callTauri<BackendStartResult>('backend_restart')
    },
    getBackendHealth() {
      return callTauri<BackendHealth>('backend_health')
    },
  }
}
