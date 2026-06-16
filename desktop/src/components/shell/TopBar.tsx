import { Moon, Sun, Monitor, Palette } from 'lucide-react'

import { getBridgeRuntimeLabel } from '@/bridge'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import { BackendStatusBadge } from '@/components/backend/BackendStatusBadge'
import { StatusPill } from '@/components/shell/StatusPill'
import { SimpleSelect } from '@/components/ui/simple-select'
import { themeModes, themePresets } from '@/theme/theme-presets'
import { useTheme } from '@/theme/use-theme'

export function TopBar({ title }: { title: string }) {
  const { mode, preset, setMode, setPreset } = useTheme()
  const { backendStatus } = useBackendStatus()

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border/70 bg-background/88 px-6 backdrop-blur">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        <p className="text-xs text-muted-foreground">Offline-first desktop UI preview</p>
      </div>
      <div className="flex items-center gap-3">
        <StatusPill />
        <BadgeLike>{getBridgeRuntimeLabel()}</BadgeLike>
        <BackendStatusBadge status={backendStatus} />
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          {mode === 'dark' ? <Moon className="h-3.5 w-3.5" /> : mode === 'light' ? <Sun className="h-3.5 w-3.5" /> : <Monitor className="h-3.5 w-3.5" />}
          <SimpleSelect
            ariaLabel="Appearance"
            value={mode}
            onValueChange={(value) => setMode(value as typeof mode)}
            options={themeModes}
            className="h-8 w-28 text-xs"
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Palette className="h-3.5 w-3.5" />
          <SimpleSelect
            ariaLabel="Theme Preset"
            value={preset}
            onValueChange={(value) => setPreset(value as typeof preset)}
            options={themePresets}
            className="h-8 w-28 text-xs"
          />
        </label>
      </div>
    </header>
  )
}

function BadgeLike({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground">
      {children}
    </span>
  )
}
