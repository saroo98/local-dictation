import { useRuntimeState } from '@/bridge/useRuntimeState'
import type { AppState, BackendStatusKind } from '@/bridge/types'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/cn'

const labels: Record<AppState['status'], string> = {
  idle: 'Idle',
  recording: 'Recording',
  transcribing: 'Transcribing',
  'paste-ready': 'Paste ready',
  error: 'Error',
}

const statusClasses: Record<AppState['status'], string> = {
  idle: 'border border-border bg-secondary text-secondary-foreground shadow-sm',
  recording: 'border border-destructive/30 bg-destructive text-destructive-foreground shadow-sm',
  transcribing: 'border border-primary/30 bg-primary/10 text-foreground shadow-sm',
  'paste-ready': 'border border-primary/30 bg-primary text-primary-foreground shadow-sm',
  error: 'border border-destructive bg-destructive text-destructive-foreground shadow-sm',
}

const backendLabels: Partial<Record<BackendStatusKind, string>> = {
  not_running: 'Backend off',
  starting: 'Starting',
  unhealthy: 'Backend issue',
  stopping: 'Stopping',
  error: 'Backend error',
}

const backendClasses: Partial<Record<BackendStatusKind, string>> = {
  not_running: 'border border-border bg-secondary text-secondary-foreground shadow-sm',
  starting: 'border border-amber-300/70 bg-amber-100 text-amber-900 shadow-sm dark:border-amber-400/30 dark:bg-amber-500/15 dark:text-amber-200',
  unhealthy: 'border border-amber-300/70 bg-amber-100 text-amber-900 shadow-sm dark:border-amber-400/30 dark:bg-amber-500/15 dark:text-amber-200',
  stopping: 'border border-border bg-secondary text-secondary-foreground shadow-sm',
  error: 'border border-destructive bg-destructive text-destructive-foreground shadow-sm',
}

export function StatusPill() {
  const { state, backendStatus } = useRuntimeState()

  if (backendStatus && backendStatus.status !== 'ready') {
    return (
      <Badge
        variant="secondary"
        className={cn(
          'min-w-14 justify-center',
          backendClasses[backendStatus.status] ?? 'border border-border bg-secondary text-secondary-foreground',
        )}
      >
        {backendLabels[backendStatus.status] ?? backendStatus.status}
      </Badge>
    )
  }

  return (
    <Badge
      variant="secondary"
      role="status"
      aria-live="polite"
      className={cn(
        'min-w-14 justify-center',
        state ? statusClasses[state.connected === false ? 'error' : state.status] : 'border border-border bg-secondary text-secondary-foreground',
      )}
    >
      {state?.connected === false ? 'Disconnected' : state?.loading ? 'Loading' : state ? labels[state.status] : 'Loading'}
    </Badge>
  )
}
