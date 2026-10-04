import type { AppState, BackendHealth, BackendStatus, Bridge, HistoryEntry, ModelInfo, ModelOrder, Settings } from '@/bridge/types'
import { historyFixtures } from '@/fixtures/history'
import { modelFixtures } from '@/fixtures/models'
import { defaultSettings, languageChoices, textFormatChoices } from '@/fixtures/settings'
import { copyText } from '@/lib/clipboard'
import { validHotkey } from '@/lib/hotkey'

const settingsKey = 'local-dictation-mock-settings'
const nativeOnly = 'This action requires the native app. Browser mode cannot access local folders or create export files.'

function copySettings(settings: Settings): Settings {
  return { ...settings, bubble_position: settings.bubble_position ? [...settings.bubble_position] : null, custom_models: settings.custom_models.map((model) => ({ ...model })) }
}

function loadStoredSettings(): Settings {
  try {
    const stored = JSON.parse(localStorage.getItem(settingsKey) ?? '{}') as Partial<Settings>
    return copySettings({ ...defaultSettings, ...stored })
  } catch { return copySettings(defaultSettings) }
}

export function createMockBridge(): Bridge {
  let settings = loadStoredSettings()
  let history: HistoryEntry[] = historyFixtures.map((entry) => ({ ...entry }))
  let state: AppState = {
    recording: false, transcribing: false, waiting_for_target_click: false, status: 'idle',
    latestTranscript: history[0]?.text ?? '', activeModel: settings.model, activeLanguage: settings.language,
    connected: true, loading: false, error: '', recording_ready: true, history_revision: 0,
  }
  let transcriptionTimer: number | undefined
  let operation = 0
  const models = modelFixtures.map((model) => ({ ...model }))
  const listeners = new Set<(next: AppState) => void>()
  const health: BackendHealth = {
    version: '0.1.0-browser-mock', pid: 0, status: 'idle', protocol_version: 4,
    backend_owner: 'browser-mock', model: settings.model, language: settings.language, device: 'mock', uptime_seconds: 0,
  }
  const backendStatus: BackendStatus = {
    status: 'ready', owned: false,
    message: 'Mock UI backend simulated. Tauri runtime is required to start Python.',
    log_path: 'C:\\local-dictation\\dictation_debug.log', health,
  }

  function emit(next: AppState) {
    state = next
    listeners.forEach((listener) => listener({ ...state }))
  }

  function persist(next: Settings) {
    localStorage.setItem(settingsKey, JSON.stringify(next))
    settings = copySettings(next)
  }

  function allModels(): ModelInfo[] {
    return [...models, ...settings.custom_models.map((model, index): ModelInfo => ({
      tier: model.name, model_name: model.name, repo_id: model.source,
      description: 'Custom faster-whisper/CTranslate2 model preview.', cache_dir: model.source,
      available: true, revision: 'custom', size_bytes: 0, size_text: 'Custom', source_type: 'custom', custom: true,
      speed_rank: 100 + index, accuracy_rank: 100 + index, download_status: 'installed', download_error: '',
    }))]
  }

  function requireIdle() {
    if (state.loading || state.transcribing || state.recording) throw new Error('The mock backend is busy recording or transcribing.')
  }

  function cancelTranscription() {
    operation += 1
    if (transcriptionTimer !== undefined) window.clearTimeout(transcriptionTimer)
    transcriptionTimer = undefined
  }

  return {
    async getSettings() { return copySettings(settings) },
    async saveSettings(patch) {
      if (state.loading || ((patch.model !== undefined || patch.device_mode !== undefined) && (state.recording || state.transcribing))) {
        throw new Error('The mock backend is busy recording or transcribing.')
      }
      const next = copySettings({ ...settings, ...patch })
      if (!languageChoices.includes(next.language)) throw new Error('Unsupported input language.')
      if (!textFormatChoices.includes(next.text_format)) throw new Error('Unsupported text format.')
      if (!['auto', 'cuda', 'cpu'].includes(next.device_mode)) throw new Error('Unsupported device mode.')
      if (!validHotkey(next.hotkey)) throw new Error('Invalid shortcut. Use a key such as <ctrl>+<space>.')
      next.hotkey = next.hotkey.trim().toLowerCase()
      persist(next)
      emit({ ...state, activeModel: settings.model, activeLanguage: settings.language, error: '' })
      return copySettings(settings)
    },
    async pickExportFolder() { throw new Error(nativeOnly) },
    async getHistory() { return history.map((entry) => ({ ...entry })) },
    async clearHistory() {
      history = []
      emit({ ...state, latestTranscript: '', history_revision: (state.history_revision ?? 0) + 1 })
    },
    async exportHistory() { throw new Error(nativeOnly) },
    async getModels(order: ModelOrder) {
      return allModels().map((model) => ({
        ...model, download_status: model.available ? 'installed' : (model.download_status ?? 'idle'), download_error: model.download_error ?? '',
      })).sort((a, b) => order === 'Speed' ? a.speed_rank - b.speed_rank : a.accuracy_rank - b.accuracy_rank)
    },
    async downloadModel(choice) {
      const model = models.find((item) => item.tier === choice)
      if (!model) throw new Error('Unknown model: ' + choice)
      if (model.available || model.download_status === 'downloading') return
      model.download_status = 'downloading'
      window.setTimeout(() => { model.available = true; model.download_status = 'installed' }, 1500)
    },
    async openModelFolder() { throw new Error(nativeOnly) },
    async copyModelPath(choice) {
      const model = allModels().find((item) => item.tier === choice)
      if (!model) throw new Error('Unknown model: ' + choice)
      if (!model.cache_dir) throw new Error('No local model path is available.')
      await copyText(model.cache_dir)
    },
    async addCustomModel(name, source) {
      const trimmedName = name.trim()
      const trimmedSource = source.trim()
      if (!trimmedName || !trimmedSource) throw new Error('Name and source are required.')
      if (allModels().some((item) => item.tier.toLowerCase() === trimmedName.toLowerCase())) throw new Error('Custom model names must be unique.')
      persist({ ...settings, custom_models: [...settings.custom_models, { name: trimmedName, source: trimmedSource }] })
    },
    async getState() { return { ...state } },
    onState(callback) {
      listeners.add(callback)
      callback({ ...state })
      return () => { listeners.delete(callback) }
    },
    async startRecording() {
      requireIdle()
      cancelTranscription()
      emit({ ...state, recording: true, transcribing: false, waiting_for_target_click: false, status: 'recording', error: '' })
    },
    async stopRecording() {
      if (!state.recording) throw new Error('The mock backend is not recording.')
      cancelTranscription()
      const currentOperation = operation
      emit({ ...state, recording: false, transcribing: true, status: 'transcribing' })
      transcriptionTimer = window.setTimeout(() => {
        if (currentOperation !== operation || !state.transcribing) return
        transcriptionTimer = undefined
        const text = 'Mock transcript created at ' + new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + '.'
        history = [{ text, created_at: new Date().toISOString() }, ...history].slice(0, 5)
        emit({ ...state, recording: false, transcribing: false, waiting_for_target_click: true,
          status: 'paste-ready', latestTranscript: text, history_revision: (state.history_revision ?? 0) + 1 })
      }, 1500)
    },
    async toggleRecording() { if (state.recording) await this.stopRecording(); else await this.startRecording() },
    async retryResources() {
      requireIdle()
      cancelTranscription()
      emit({ ...state, loading: true, recording_ready: false, error: '' })
      const currentOperation = operation
      await new Promise<void>((resolve) => {
        window.setTimeout(() => {
          if (currentOperation === operation) emit({ ...state, loading: false, recording_ready: true, status: 'idle' })
          resolve()
        }, 300)
      })
    },
    async getBackendStatus() { return { ...backendStatus, health: { ...health, status: state.status, model: settings.model, language: settings.language } } },
    async startBackend() { throw new Error('Backend process controls require the Tauri runtime.') },
    async stopBackend() { throw new Error('Backend process controls require the Tauri runtime.') },
    async restartBackend() { throw new Error('Backend process controls require the Tauri runtime.') },
    async getBackendHealth() { return { ...health, status: state.status, model: settings.model, language: settings.language } },
  }
}
