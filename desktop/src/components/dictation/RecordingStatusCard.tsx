import { AudioLines, ClipboardCheck, Loader2, MousePointerClick } from 'lucide-react'

import type { AppState } from '@/bridge/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function RecordingStatusCard({ state }: { state: AppState | null }) {
  const status = state?.status ?? 'idle'
  const Icon =
    status === 'recording' ? AudioLines : status === 'transcribing' ? Loader2 : status === 'paste-ready' ? ClipboardCheck : MousePointerClick

  return (
    <Card className="ld-card-shadow">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" strokeWidth={1.8} />
          {status === 'paste-ready' ? 'Ready to paste' : status.charAt(0).toUpperCase() + status.slice(1)}
        </CardTitle>
        <CardDescription>
          This is mock state only. The existing Python/Tkinter app still owns real recording.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-sm">
        <Info label="Model" value={state?.activeModel ?? 'Balanced'} />
        <Info label="Language" value={state?.activeLanguage ?? 'English (US)'} />
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
