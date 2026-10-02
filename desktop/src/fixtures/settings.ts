import type { Settings } from '@/bridge/types'

export const defaultSettings: Settings = {
  language: 'English (US)',
  model: 'Balanced',
  model_order: 'Speed',
  device_mode: 'auto',
  theme: 'Dark Mode',
  opacity: 100,
  text_format: 'Plain Text',
  save_location: '',
  hotkey: '<ctrl>+<alt>+d',
  bubble_position: [0, 0],
  custom_models: [],
}

export const languageChoices = ['English (US)', 'Auto Detect', 'Kurdish', 'Persian', 'Arabic']
export const textFormatChoices = ['Plain Text', 'Markdown (.md)']
export const deviceModeChoices = [
  { label: 'Auto (CUDA -> CPU)', value: 'auto' },
  { label: 'CUDA (NVIDIA only)', value: 'cuda' },
  { label: 'CPU only', value: 'cpu' },
  { label: 'Vulkan (not supported by faster-whisper backend)', value: 'vulkan', disabled: true },
]
