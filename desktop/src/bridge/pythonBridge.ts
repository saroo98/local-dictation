import { invoke, isTauri } from '@tauri-apps/api/core'
import { watchCurrentWindowVisibility } from '@/tauri/windowControls'

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
} from '@/bridge/types'

interface BridgeResponse<T> {
  ok: boolean
  data?: T
  error?: string
}

const localBridgeUnavailableMessage = 'Local Dictation is not running. Start or retry the backend in Help/About.'
const incompatibleLocalBridgeMessage =
  'Local Dictation is running, but its bridge protocol is incompatible. Close the old Python app, then start the backend from this build.'

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
  const listeners = new Set<(state: AppState) => void>()
  let lastState: AppState | undefined
  let previous = ''
  let inFlight: Promise<AppState> | undefined
  let timer: number | undefined
  let polling = false
  let generation = 0
  let stateVersion = 0
  let nativeVisible: boolean | undefined
  let visibilityVersion = 0
  let unlistenVisibility: (() => void) | undefined

  function publish(state: AppState) {
    lastState = state
    const serialized = JSON.stringify(state)
    if (serialized === previous) return
    previous = serialized
    listeners.forEach((listener) => listener(state))
  }

  function readState(): Promise<AppState> {
    if (inFlight) return inFlight
    const version = stateVersion
    inFlight = callPython<AppState>('get-state').then((next) => {
      const state = { ...next, connected: true, connection_error: undefined }
      if (version === stateVersion) publish(state)
      return state
    }).catch((error: unknown) => {
      if (version === stateVersion) {
        publish({
          recording: false, transcribing: false, waiting_for_target_click: false,
          status: 'idle', latestTranscript: '', activeModel: '', activeLanguage: '',
          ...lastState, connected: false, connection_error: errorMessage(error),
        })
      }
      throw error
    }).finally(() => { inFlight = undefined })
    return inFlight
  }

  function visible() {
    return nativeVisible ?? !document.hidden
  }

  async function poll() {
    if (polling || listeners.size === 0 || !visible()) return
    polling = true
    const currentGeneration = generation
    const version = stateVersion
    try { await readState() } catch { /* Connection failure is published separately. */ }
    finally { polling = false }
    if (currentGeneration !== generation) { refreshVisibleState(); return }
    if (currentGeneration === generation && listeners.size > 0 && visible()) {
      timer = window.setTimeout(() => { timer = undefined; void poll() }, version === stateVersion ? 750 : 0)
    }
  }

  function refreshVisibleState() {
    if (timer !== undefined) window.clearTimeout(timer)
    timer = undefined
    if (visible()) void poll()
  }

  function visibilityChanged() { refreshVisibleState() }

  async function startPolling() {
    const currentGeneration = generation
    document.addEventListener('visibilitychange', visibilityChanged)
    if (isTauri()) {
      try {
        const off = await watchCurrentWindowVisibility((visible) => {
          visibilityVersion += 1
          nativeVisible = visible
          refreshVisibleState()
        })
        if (currentGeneration !== generation) { off(); return }
        unlistenVisibility = off
        const version = visibilityVersion
        const initial = await callTauri<boolean>('current_window_visible')
        if (currentGeneration !== generation || version !== visibilityVersion) return
        if (typeof initial === 'boolean') nativeVisible = initial
      } catch { /* DOM visibility still works if native visibility is unavailable. */ }
    }
    if (currentGeneration === generation) refreshVisibleState()
  }

  async function action<T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> {
    stateVersion += 1
    try { return await callPython<T>(cmd, args) }
    finally { stateVersion += 1; refreshVisibleState() }
  }

  return {
    getSettings() {
      return callPython<Settings>('get-settings')
    },
    saveSettings(settings, options) {
      return action<Settings>('set-settings', { settings, ...(options?.recover ? { recover: true } : {}) })
    },
    pickExportFolder() {
      return callTauri<string | null>('pick_export_folder')
    },
    getHistory() {
      return callPython<HistoryEntry[]>('get-history')
    },
    clearHistory() {
      return action<HistoryEntry[]>('clear-history').then(() => undefined)
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
      return action<Settings>('add-custom-model', { name, source }).then(() => undefined)
    },
    async getState() {
      for (;;) {
        const version = stateVersion
        const next = await readState()
        if (version === stateVersion) return next
      }
    },
    onState(callback) {
      listeners.add(callback)
      if (lastState) callback(lastState)
      if (listeners.size === 1) { generation += 1; void startPolling() }
      return () => {
        listeners.delete(callback)
        if (listeners.size === 0) {
          generation += 1
          if (timer !== undefined) window.clearTimeout(timer)
          timer = undefined
          unlistenVisibility?.()
          unlistenVisibility = undefined
          document.removeEventListener('visibilitychange', visibilityChanged)
        }
      }
    },
    startRecording() {
      return action<{ accepted: boolean }>('start-recording').then(() => undefined)
    },
    stopRecording() {
      return action<{ accepted: boolean }>('stop-recording').then(() => undefined)
    },
    toggleRecording() {
      return action<{ accepted: boolean }>('toggle-recording').then(() => undefined)
    },
    retryResources() {
      return action<{ accepted: boolean }>('retry-resources').then(() => undefined)
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
