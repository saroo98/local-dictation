import { Save } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import { useRuntimeState } from '@/bridge/useRuntimeState'
import type { DeviceMode, ModelInfo, Settings, ThemeMode, ThemePreset } from '@/bridge/types'
import { HotkeyInput } from '@/components/settings/HotkeyInput'
import { SettingsField } from '@/components/settings/SettingsField'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SimpleSelect } from '@/components/ui/simple-select'
import { deviceModeChoices, languageChoices, textFormatChoices } from '@/fixtures/settings'
import { themeModes, themePresets } from '@/theme/theme-presets'
import { useTheme } from '@/theme/use-theme'
import { validHotkey } from '@/lib/hotkey'

export function SettingsPage() {
  const bridge = useBridge()
  const theme = useTheme()
  const { state, backendReady } = useRuntimeState()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [browsing, setBrowsing] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const patch = useRef<Partial<Settings>>({})
  const savePending = useRef(false)
  const readId = useRef(0)
  const savedTimer = useRef<number | undefined>(undefined)
  const canRead = backendReady && state?.connected !== false
  const formDisabled = saving || !canRead || Boolean(state?.loading)

  const loadSettings = useCallback(async () => {
    if (savePending.current) return
    const id = ++readId.current
    try {
      const next = await bridge.getSettings()
      if (id === readId.current) {
        setSettings({ ...next, ...patch.current })
        setLoadError(null)
      }
    } catch (error) {
      if (id === readId.current) setLoadError(error instanceof Error ? error.message : 'Could not load settings')
    }
  }, [bridge])

  useEffect(() => {
    if (canRead) void loadSettings()
    return () => { readId.current += 1 }
  }, [canRead, loadSettings])

  useEffect(() => () => { if (savedTimer.current !== undefined) window.clearTimeout(savedTimer.current) }, [])

  const modelOrder = settings?.model_order

  useEffect(() => {
    if (!modelOrder || !canRead) return undefined

    let cancelled = false
    void bridge
      .getModels(modelOrder)
      .then((nextModels) => {
        if (!cancelled) { setModels(nextModels); setModelsError(null) }
      })
      .catch((error: unknown) => {
        if (!cancelled) setModelsError(error instanceof Error ? error.message : 'Could not load models')
      })

    return () => {
      cancelled = true
    }
  }, [bridge, canRead, modelOrder])

  function edit<K extends keyof Settings>(key: K, value: Settings[K]) {
    if (savePending.current) return
    patch.current = { ...patch.current, [key]: value }
    setSettings((current) => current ? { ...current, [key]: value } : current)
    setSaved(false)
    setSaveError(null)
  }

  async function browse() {
    if (browsing || savePending.current) return
    setBrowsing(true)
    try {
      const folder = await bridge.pickExportFolder()
      if (folder !== null) edit('save_location', folder)
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not choose a folder') }
    finally { setBrowsing(false) }
  }

  if (!settings) return (
    <div>
      <PageHeader title="Settings" description={loadError ?? (backendReady ? 'Loading settings...' : 'Waiting for the backend...')} />
      {loadError ? <Button variant="outline" onClick={() => void loadSettings()} disabled={!canRead}>Retry settings</Button> : null}
    </div>
  )

  async function saveChanges() {
    if (!settings || savePending.current || formDisabled) return
    if (!validHotkey(settings.hotkey)) {
      setSaveError('Invalid shortcut. Use a letter, function or arrow key, such as <ctrl>+<space>.')
      return
    }
    savePending.current = true
    readId.current += 1
    setSaving(true)
    setSaveError(null)
    try {
      const savedSettings = await bridge.saveSettings(patch.current, { recover: true })
      patch.current = {}
      setSettings(savedSettings)
      setSaved(true)
      toast.success('Settings saved')
      if (savedTimer.current !== undefined) window.clearTimeout(savedTimer.current)
      savedTimer.current = window.setTimeout(() => setSaved(false), 1800)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not save settings'
      setSaveError(message)
      toast.error(message)
    } finally { savePending.current = false; setSaving(false) }
  }

  return (
    <div>
      <PageHeader title="Settings" description="Transcription, output, and shortcut controls." />
      {state?.settings_error ? <p role="alert" className="mb-4 text-sm text-destructive">
        {state.settings_error} Save changes to recover these settings. The unreadable file will be backed up first.
      </p> : null}
      {loadError || !canRead ? (
        <div role="alert" className="mb-4 flex items-center gap-3 text-sm text-destructive">
          <p>{loadError ?? state?.connection_error ?? 'Waiting for the backend...'}</p>
          <Button variant="outline" onClick={() => void loadSettings()} disabled={!canRead || saving}>Retry settings</Button>
        </div>
      ) : null}
      <fieldset disabled={formDisabled || browsing} className="min-w-0 space-y-4">
        <SettingsSection title="Transcription">
          <SettingsField id="language" label="Input Language">
            <SimpleSelect
              id="language"
              value={settings.language}
              onValueChange={(language) => edit('language', language)}
              options={languageChoices.map((choice) => ({ label: choice, value: choice }))}
            />
          </SettingsField>
          <SettingsField id="model" label="Model">
            <SimpleSelect
              id="model"
              value={settings.model}
              onValueChange={(model) => edit('model', model)}
              options={modelOptions(models, settings.model)}
            />
          </SettingsField>
          <SettingsField id="model-order" label="Model Order">
            <SimpleSelect
              id="model-order"
              value={settings.model_order}
              onValueChange={(modelOrder) => edit('model_order', modelOrder as Settings['model_order'])}
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
              onValueChange={(deviceMode) => edit('device_mode', deviceMode as DeviceMode)}
              options={deviceModeChoices}
            />
          </SettingsField>
        </SettingsSection>

        <SettingsSection title="Interface & Output">
          <SettingsField id="appearance" label="Appearance">
            <SimpleSelect
              id="appearance"
              ariaLabel="Appearance"
              value={theme.mode}
              onValueChange={(mode) => theme.setMode(mode as ThemeMode)}
              options={themeModes}
            />
          </SettingsField>
          <SettingsField id="theme-preset" label="Theme Preset">
            <SimpleSelect
              id="theme-preset"
              ariaLabel="Theme Preset"
              value={theme.preset}
              onValueChange={(preset) => theme.setPreset(preset as ThemePreset)}
              options={themePresets}
            />
          </SettingsField>
          <SettingsField id="text-format" label="Text Format">
            <SimpleSelect
              id="text-format"
              value={settings.text_format}
              onValueChange={(textFormat) => edit('text_format', textFormat)}
              options={textFormatChoices.map((choice) => ({ label: choice, value: choice }))}
            />
          </SettingsField>
          <SettingsField id="save-location" label="Save Location">
            <div className="flex gap-2">
              <Input
                id="save-location"
                value={settings.save_location}
                onChange={(event) => edit('save_location', event.target.value)}
              />
              <Button type="button" variant="outline" onClick={() => void browse()} disabled={browsing}>
                {browsing ? 'Choosing...' : 'Browse'}
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
            <HotkeyInput value={settings.hotkey} onChange={(hotkey) => edit('hotkey', hotkey)} disabled={formDisabled} />
          </SettingsField>
        </SettingsSection>
      </fieldset>
      {modelsError ? <p role="alert" className="mt-3 text-sm text-destructive">{modelsError}</p> : null}
      {saveError ? <p role="alert" className="mt-3 text-sm text-destructive">{saveError}</p> : null}
      <div className="mt-5 flex justify-end gap-3">
        {saved ? <span className="self-center text-sm text-primary">Settings saved</span> : null}
        <Button type="button" disabled={formDisabled || browsing} onClick={() => void saveChanges()}>
          <Save className="h-4 w-4" /> {saving ? 'Saving...' : 'Save changes'}
        </Button>
      </div>
    </div>
  )
}

function modelOptions(models: ModelInfo[], currentModel: string) {
  if (models.length === 0) return [{ label: currentModel, value: currentModel }]
  const source = models

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
