export type ModelOrder = 'Speed' | 'Accuracy'
export type ThemeMode = 'light' | 'dark' | 'system'
export type ThemePreset = 'neutral' | 'green' | 'blue'
export type AppStatus = 'idle' | 'recording' | 'transcribing' | 'paste-ready' | 'error'
export type DownloadStatus = 'idle' | 'downloading' | 'installed' | 'error'
export type BackendStatusKind = 'not_running' | 'starting' | 'ready' | 'unhealthy' | 'stopping' | 'error'
export type DeviceMode = 'auto' | 'cuda' | 'cpu'

export interface Settings {
  language: string
  model: string
  model_order: ModelOrder
  device_mode: DeviceMode
  theme: string
  opacity: number
  text_format: string
  save_location: string
  hotkey: string
  bubble_position: [number, number] | null
  custom_models: CustomModel[]
}

export interface CustomModel {
  name: string
  source: string
}

export interface ModelInfo {
  tier: string
  model_name: string
  repo_id: string
  description: string
  cache_dir: string
  available: boolean
  revision: string
  size_bytes: number
  size_text: string
  source_type: 'builtin' | 'custom' | 'repo' | 'local'
  custom: boolean
  speed_rank: number
  accuracy_rank: number
  download_status?: DownloadStatus
  download_error?: string
}

export interface HistoryEntry {
  text: string
  created_at: string | null
}

export interface AppState {
  recording: boolean
  transcribing: boolean
  waiting_for_target_click: boolean
  status: AppStatus
  latestTranscript: string
  activeModel: string
  activeLanguage: string
  loading?: boolean
  error?: string
  settings_error?: string
  history_error?: string
  recording_ready?: boolean
  history_revision?: number
  connected?: boolean
  connection_error?: string
}

export interface BackendHealth {
  version: string
  pid: number
  status: AppStatus
  protocol_version: number
  backend_owner: string
  model: string
  language: string
  device: string
  uptime_seconds: number
  launch_id?: string
}

export interface BackendStatus {
  status: BackendStatusKind
  owned: boolean
  message: string
  log_path: string
  health?: BackendHealth
  launch_kind?: 'sidecar' | 'python-fallback' | 'existing' | 'managed' | string
  starting_seconds?: number
  last_error?: string
}

export type BackendStartResult = BackendStatus
export type BackendStopResult = BackendStatus

export interface Bridge {
  getSettings(): Promise<Settings>
  saveSettings(patch: Partial<Settings>, options?: { recover?: boolean }): Promise<Settings>
  pickExportFolder(): Promise<string | null>
  getHistory(): Promise<HistoryEntry[]>
  clearHistory(): Promise<void>
  exportHistory(format: 'txt' | 'md'): Promise<string>
  getModels(order: ModelOrder): Promise<ModelInfo[]>
  downloadModel(choice: string): Promise<void>
  openModelFolder(choice: string): Promise<void>
  copyModelPath(choice: string): Promise<void>
  addCustomModel(name: string, source: string): Promise<void>
  getState(): Promise<AppState>
  onState(callback: (state: AppState) => void): () => void
  startRecording(): Promise<void>
  stopRecording(): Promise<void>
  toggleRecording(): Promise<void>
  retryResources(): Promise<void>
  getBackendStatus(): Promise<BackendStatus>
  startBackend(): Promise<BackendStartResult>
  stopBackend(): Promise<BackendStopResult>
  restartBackend(): Promise<BackendStartResult>
  getBackendHealth(): Promise<BackendHealth>
}
