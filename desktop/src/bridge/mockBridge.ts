import type { AppState, Bridge, HistoryEntry, ModelInfo, ModelOrder, Settings, UpdateCheck } from '@/bridge/types'
import { historyFixtures } from '@/fixtures/history'
import { modelFixtures } from '@/fixtures/models'
import { defaultSettings } from '@/fixtures/settings'

const settingsKey = 'local-dictation-mock-settings'

function loadStoredSettings(): Settings {
  const stored = localStorage.getItem(settingsKey)
  if (!stored) return { ...defaultSettings, custom_models: [...defaultSettings.custom_models] }

  try {
    return { ...defaultSettings, ...JSON.parse(stored) } as Settings
  } catch {
    return { ...defaultSettings, custom_models: [...defaultSettings.custom_models] }
  }
}

export function createMockBridge(): Bridge {
  let settings = loadStoredSettings()
  let history: HistoryEntry[] = [...historyFixtures]
  let state: AppState = {
    recording: false,
    transcribing: false,
    waiting_for_target_click: false,
    status: 'idle',
    latestTranscript: history[0]?.text ?? '',
    activeModel: settings.model,
    activeLanguage: settings.language,
  }
  const listeners = new Set<(next: AppState) => void>()

  function emit(next: AppState) {
    state = next
    listeners.forEach((listener) => listener(state))
  }

  async function finishTranscription() {
    const text = `Mock transcript created at ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}.`
    history = [{ text, created_at: new Date().toISOString() }, ...history]
    emit({
      ...state,
      recording: false,
      transcribing: false,
      waiting_for_target_click: true,
      status: 'paste-ready',
      latestTranscript: text,
    })
  }

  return {
    async getSettings() {
      return { ...settings, custom_models: [...settings.custom_models] }
    },
    async saveSettings(nextSettings) {
      settings = { ...nextSettings, custom_models: [...nextSettings.custom_models] }
      localStorage.setItem(settingsKey, JSON.stringify(settings))
      emit({ ...state, activeModel: settings.model, activeLanguage: settings.language })
    },
    async getHistory() {
      return [...history]
    },
    async clearHistory() {
      history = []
      emit({ ...state, latestTranscript: '' })
    },
    async exportHistory(format) {
      if (format === 'md') {
        return history.map((entry) => `- **${entry.created_at}** ${entry.text}`).join('\n')
      }
      return history.map((entry) => `[${entry.created_at}] ${entry.text}`).join('\n')
    },
    async getModels(order: ModelOrder) {
      const customModels: ModelInfo[] = settings.custom_models.map((model, index) => ({
        tier: model.name,
        model_name: model.name,
        repo_id: model.source,
        description: 'Custom faster-whisper/CTranslate2 model.',
        cache_dir: model.source,
        available: true,
        revision: 'custom',
        size_bytes: 0,
        size_text: 'Custom',
        source_type: 'custom',
        custom: true,
        speed_rank: 100 + index,
        accuracy_rank: 100 + index,
      }))
      return [...modelFixtures, ...customModels].sort((a, b) =>
        order === 'Speed' ? a.speed_rank - b.speed_rank : a.accuracy_rank - b.accuracy_rank,
      )
    },
    async downloadModel() {
      await Promise.resolve()
    },
    async openModelFolder() {
      await Promise.resolve()
    },
    async copyModelPath(choice) {
      const model = [...modelFixtures].find((item) => item.tier === choice)
      await navigator.clipboard.writeText(model?.cache_dir ?? '')
    },
    async addCustomModel(name, source) {
      const trimmedName = name.trim()
      const trimmedSource = source.trim()
      if (!trimmedName || !trimmedSource) throw new Error('Name and source are required.')
      if (settings.custom_models.some((item) => item.name.toLowerCase() === trimmedName.toLowerCase())) {
        throw new Error('Custom model names must be unique.')
      }
      settings = {
        ...settings,
        custom_models: [...settings.custom_models, { name: trimmedName, source: trimmedSource }],
      }
      localStorage.setItem(settingsKey, JSON.stringify(settings))
    },
    async getState() {
      return { ...state }
    },
    onState(callback) {
      listeners.add(callback)
      return () => listeners.delete(callback)
    },
    async startRecording() {
      emit({
        ...state,
        recording: true,
        transcribing: false,
        waiting_for_target_click: false,
        status: 'recording',
      })
    },
    async stopRecording() {
      if (!state.recording) return
      emit({ ...state, recording: false, transcribing: true, status: 'transcribing' })
      window.setTimeout(() => {
        void finishTranscription()
      }, 1500)
    },
    async toggleRecording() {
      if (state.recording) {
        await this.stopRecording()
      } else {
        await this.startRecording()
      }
    },
    async checkForUpdates(): Promise<UpdateCheck> {
      return { current: '0.1.0-phase-1', latest: '0.1.0-phase-1' }
    },
  }
}
