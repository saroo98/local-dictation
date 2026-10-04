import type { BackendStatus, BackendStatusKind } from '@/bridge/types'
import { Badge } from '@/components/ui/badge'

const statusLabels: Record<BackendStatusKind, string> = {
  not_running: 'Backend not running',
  starting: 'Backend starting',
  ready: 'Local backend ready',
  unhealthy: 'Backend unhealthy',
  stopping: 'Backend stopping',
  error: 'Backend error',
}

function labelForStatus(status: BackendStatus | null): string {
  if (!status) return 'Backend checking'
  if (status.health?.backend_owner === 'browser-mock') return 'Mock backend'
  if (status.status === 'ready') return 'Local backend ready'
  return statusLabels[status.status]
}

export function BackendStatusBadge({ status }: { status: BackendStatus | null }) {
  const variant = status?.status === 'ready' ? 'default' : status?.status === 'error' ? 'destructive' : 'secondary'

  return <Badge variant={variant}>{labelForStatus(status)}</Badge>
}
