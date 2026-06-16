import { useEffect, useState } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
import type { AppState, HistoryEntry } from '@/bridge/types'
import { BubblePreview } from '@/components/dictation/BubblePreview'
import { RecordButton } from '@/components/dictation/RecordButton'
import { RecordingStatusCard } from '@/components/dictation/RecordingStatusCard'
import { TranscriptPreview } from '@/components/dictation/TranscriptPreview'
import { PageHeader } from '@/components/shell/PageHeader'
import { Card, CardContent } from '@/components/ui/card'

export function RecordingPage() {
  const bridge = useBridge()
  const [state, setState] = useState<AppState | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])

  useEffect(() => {
    let mounted = true
    void bridge.getState().then((next) => {
      if (mounted) setState(next)
    })
    void bridge.getHistory().then((next) => {
      if (mounted) setHistory(next)
    })
    const off = bridge.onState((next) => {
      setState(next)
      void bridge.getHistory().then(setHistory)
    })
    return () => {
      mounted = false
      off()
    }
  }, [bridge])

  return (
    <div>
      <PageHeader
        title="Recording"
        description="A browser-reviewable mock of the future Tauri desktop recording surface. Real dictation stays in the Python app for Phase 1."
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          <Card className="ld-card-shadow">
            <CardContent className="flex flex-col items-center gap-5 p-8 text-center">
              <RecordButton
                state={state}
                onToggle={() => {
                  void bridge.toggleRecording()
                }}
              />
              <div>
                <p className="font-medium">Click once to record, click again to stop.</p>
                <p className="mt-1 text-sm text-muted-foreground">The mock flow transcribes after stop and keeps output clipboard-ready.</p>
              </div>
            </CardContent>
          </Card>
          <RecordingStatusCard state={state} />
          <TranscriptPreview text={state?.latestTranscript ?? ''} onOpenHistory={() => undefined} />
        </div>
        <div>
          <p className="mb-3 text-sm font-medium text-muted-foreground">Floating bubble and transcript popover preview</p>
          <BubblePreview entries={history} />
        </div>
      </div>
    </div>
  )
}
