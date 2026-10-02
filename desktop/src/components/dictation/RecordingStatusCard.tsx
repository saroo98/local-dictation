import { AudioLines, ClipboardCheck, Loader2, MousePointerClick } from 'lucide-react'

import type { AppState } from '@/bridge/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function RecordingStatusCard({ state, mock = false }: { state: AppState | null; mock?: boolean }) {
  const status = state?.status ?? 'idle'
  const Icon =
    status === 'recording' ? AudioLines : status === 'transcribing' ? Loader2 : status === 'paste-ready' ? ClipboardCheck : MousePointerClick

  return (
    <Card className="ld-card-shadow">
      <CardHeader>
        <CardTitle role="status" aria-live="polite" className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" strokeWidth={1.8} />
          {state?.connected === false ? 'Disconnected' : state?.loading ? 'Loading resources' : !state ? 'Checking recording state' : status === 'paste-ready' ? 'Ready to paste' : status.charAt(0).toUpperCase() + status.slice(1)}
        </CardTitle>
        <CardDescription>
          {state?.connection_error || state?.error || (mock ? 'Browser preview uses simulated recording.' : 'Audio capture and transcription run locally.')}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-sm">
        <Info label="Model" value={state?.activeModel || 'Unavailable'} />
        <Info label="Language" value={state?.activeLanguage || 'Unavailable'} />
      </CardContent>
    </Card>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-secondary/60 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  )
}
