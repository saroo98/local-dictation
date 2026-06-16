import type { Settings } from '@/bridge/types'

export const defaultSettings: Settings = {
  language: 'English (US)',
  model: 'Balanced',
  model_order: 'Speed',
  theme: 'Dark Mode',
  opacity: 100,
  text_format: 'Plain Text',
  save_location: '',
  hotkey: '<ctrl>+<alt>+d',
  bubble_position: [0, 0],
  custom_models: [],
}

export const languageChoices = ['English (US)', 'Auto Detect', 'Kurdish', 'Arabic', 'Spanish']
export const textFormatChoices = ['Plain Text', 'Markdown']
