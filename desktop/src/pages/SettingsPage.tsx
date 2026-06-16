import { Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import type { Settings, ThemeMode, ThemePreset } from '@/bridge/types'
import { HotkeyInput } from '@/components/settings/HotkeyInput'
import { SettingsField } from '@/components/settings/SettingsField'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SimpleSelect } from '@/components/ui/simple-select'
import { Slider } from '@/components/ui/slider'
import { languageChoices, textFormatChoices } from '@/fixtures/settings'
import { themeModes, themePresets } from '@/theme/theme-presets'
import { useTheme } from '@/theme/use-theme'

export function SettingsPage() {
  const bridge = useBridge()
  const theme = useTheme()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    void bridge
      .getSettings()
      .then((next) => {
        setSettings(next)
        setLoadError(null)
      })
      .catch((error: unknown) => {
        setLoadError(error instanceof Error ? error.message : 'Could not load settings')
      })
  }, [bridge])

  if (!settings) return <PageHeader title="Settings" description={loadError ?? 'Loading settings...'} />

  async function saveChanges() {
    if (!settings) return
    try {
      const savedSettings = await bridge.saveSettings(settings)
      if (savedSettings) setSettings(savedSettings)
      setSaved(true)
      toast.success('Settings saved')
      window.setTimeout(() => setSaved(false), 1800)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save settings')
    }
  }

  return (
    <div>
      <PageHeader title="Settings" description="Transcription, output, and shortcut controls." />
      <div className="space-y-4">
        <SettingsSection title="Transcription">
          <SettingsField id="language" label="Input Language">
            <SimpleSelect
              id="language"
              value={settings.language}
              onValueChange={(language) => setSettings({ ...settings, language })}
              options={languageChoices.map((choice) => ({ label: choice, value: choice }))}
            />
          </SettingsField>
          <SettingsField id="model" label="Model">
            <SimpleSelect
              id="model"
              value={settings.model}
              onValueChange={(model) => setSettings({ ...settings, model })}
              options={['Fast', 'Balanced', 'High Accuracy', 'Ultra Fast English', 'Compact Multilingual', 'Medium Quality'].map((choice) => ({
                label: choice,
                value: choice,
              }))}
            />
          </SettingsField>
          <SettingsField id="model-order" label="Model Order">
            <SimpleSelect
              id="model-order"
              value={settings.model_order}
              onValueChange={(modelOrder) => setSettings({ ...settings, model_order: modelOrder as Settings['model_order'] })}
              options={['Speed', 'Accuracy'].map((choice) => ({ label: choice, value: choice }))}
            />
          </SettingsField>
        </SettingsSection>

        <SettingsSection title="Interface & Output">
          <SettingsField id="appearance" label="Appearance">
            <SimpleSelect
              id="appearance"
              aria-label="Appearance"
              value={theme.mode}
              onValueChange={(mode) => theme.setMode(mode as ThemeMode)}
              options={themeModes}
            />
          </SettingsField>
          <SettingsField id="theme-preset" label="Theme Preset">
            <SimpleSelect
              id="theme-preset"
              aria-label="Theme Preset"
              value={theme.preset}
              onValueChange={(preset) => theme.setPreset(preset as ThemePreset)}
              options={themePresets}
            />
          </SettingsField>
          <SettingsField id="opacity" label="Panel Opacity">
            <div className="flex items-center gap-4">
              <Slider
                id="opacity"
                value={[settings.opacity]}
                min={50}
                max={100}
                step={5}
                onValueChange={([opacity]) => setSettings({ ...settings, opacity: opacity ?? 100 })}
              />
              <span className="w-12 text-sm text-muted-foreground">{settings.opacity}%</span>
            </div>
          </SettingsField>
          <SettingsField id="text-format" label="Text Format">
            <SimpleSelect
              id="text-format"
              value={settings.text_format}
              onValueChange={(textFormat) => setSettings({ ...settings, text_format: textFormat })}
              options={textFormatChoices.map((choice) => ({ label: choice, value: choice }))}
            />
          </SettingsField>
          <SettingsField id="save-location" label="Save Location">
            <div className="flex gap-2">
              <Input
                id="save-location"
                value={settings.save_location}
                onChange={(event) => setSettings({ ...settings, save_location: event.target.value })}
              />
              <Button type="button" variant="outline">
                Browse
              </Button>
            </div>
          </SettingsField>
        </SettingsSection>

        <SettingsSection title="Commands & Hotkeys">
          <SettingsField
            id="hotkey"
            label="Start/Stop Key"
            help="Click the bubble to record at any time. Example hotkey: <ctrl>+<alt>+d. Leave blank to disable."
          >
            <HotkeyInput value={settings.hotkey} onChange={(hotkey) => setSettings({ ...settings, hotkey })} />
          </SettingsField>
        </SettingsSection>
      </div>
      <div className="mt-5 flex justify-end gap-3">
        {saved ? <span className="self-center text-sm text-primary">Settings saved</span> : null}
        <Button type="button" onClick={() => void saveChanges()}>
          <Save className="h-4 w-4" /> Save changes
        </Button>
      </div>
    </div>
  )
}
