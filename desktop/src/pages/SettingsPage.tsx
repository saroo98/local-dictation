import { Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import type { DeviceMode, ModelInfo, Settings, ThemeMode, ThemePreset } from '@/bridge/types'
import { HotkeyInput } from '@/components/settings/HotkeyInput'
import { SettingsField } from '@/components/settings/SettingsField'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SimpleSelect } from '@/components/ui/simple-select'
import { Slider } from '@/components/ui/slider'
import { deviceModeChoices, languageChoices, textFormatChoices } from '@/fixtures/settings'
import { themeModes, themePresets } from '@/theme/theme-presets'
import { useTheme } from '@/theme/use-theme'

export function SettingsPage() {
  const bridge = useBridge()
  const theme = useTheme()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
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

  const modelOrder = settings?.model_order

  useEffect(() => {
    if (!modelOrder) return undefined

    let cancelled = false
    void bridge
      .getModels(modelOrder)
      .then((nextModels) => {
        if (!cancelled) setModels(nextModels)
      })
      .catch(() => {
        if (!cancelled) setModels([])
      })

    return () => {
      cancelled = true
    }
  }, [bridge, modelOrder])

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
              options={modelOptions(models)}
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
          <SettingsField
            id="device-mode"
            label="Device"
            help="Auto tries CUDA first, then falls back to CPU. CUDA mode reports an error instead of silently falling back."
          >
            <SimpleSelect
              id="device-mode"
              ariaLabel="Device"
              value={settings.device_mode}
              onValueChange={(deviceMode) => setSettings({ ...settings, device_mode: deviceMode as DeviceMode })}
              options={deviceModeChoices}
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

function modelOptions(models: ModelInfo[]) {
  const fallbackModels: ModelInfo[] = [
    { tier: 'Fast', size_text: '464 MB' },
    { tier: 'Balanced', size_text: '1.62 GB' },
    { tier: 'High Accuracy', size_text: '2.88 GB' },
    { tier: 'Ultra Fast English', size_text: '79 MB' },
    { tier: 'Compact Multilingual', size_text: '145 MB' },
    { tier: 'Medium Quality', size_text: '1.53 GB' },
  ].map((model, index) => ({
    model_name: model.tier,
    repo_id: '',
    description: '',
    cache_dir: '',
    available: false,
    revision: '',
    size_bytes: 0,
    source_type: 'builtin',
    custom: false,
    speed_rank: index + 1,
    accuracy_rank: index + 1,
    ...model,
  }))
  const source = models.length > 0 ? models : fallbackModels

  return source.map((model) => {
    const label = `${model.tier} (${model.size_text})`
    return {
      label,
      value: model.tier,
      content: <ModelSelectLabel name={model.tier} size={model.size_text} />,
      selectedContent: <ModelSelectLabel name={model.tier} size={model.size_text} />,
    }
  })
}

function ModelSelectLabel({ name, size }: { name: string; size: string }) {
  return (
    <span className="grid w-full grid-cols-[minmax(0,1fr)_6.5rem] items-center gap-4">
      <span className="truncate">{name}</span>
      <span className="text-right text-muted-foreground">({size})</span>
    </span>
  )
}
