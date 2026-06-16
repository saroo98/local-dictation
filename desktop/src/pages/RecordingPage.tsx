import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { getBridgeRuntimeLabel } from '@/bridge'
import { useBridge } from '@/bridge/bridgeContext'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import type { AppState, HistoryEntry } from '@/bridge/types'
import { BubblePreview } from '@/components/dictation/BubblePreview'
import { RecordButton } from '@/components/dictation/RecordButton'
import { RecordingStatusCard } from '@/components/dictation/RecordingStatusCard'
import { TranscriptPreview } from '@/components/dictation/TranscriptPreview'
import { PageHeader } from '@/components/shell/PageHeader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent } from '@/components/ui/card'

export function RecordingPage() {
  const bridge = useBridge()
  const runtimeLabel = getBridgeRuntimeLabel()
  const { backendStatus } = useBackendStatus()
  const [state, setState] = useState<AppState | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const backendReady = backendStatus?.status === 'ready'
  const recordingDisabled = backendStatus !== null && !backendReady

  useEffect(() => {
    let mounted = true
    void bridge
      .getState()
      .then((next) => {
        if (mounted) setState(next)
      })
      .catch(() => {
        if (mounted) setState(null)
      })
    void bridge
      .getHistory()
      .then((next) => {
        if (mounted) setHistory(next)
      })
      .catch(() => {
        if (mounted) setHistory([])
      })
    const off = bridge.onState((next) => {
      setState(next)
      void bridge.getHistory().then(setHistory).catch(() => setHistory([]))
    })
    return () => {
      mounted = false
      off()
    }
  }, [bridge])

  async function toggleRecording() {
    try {
      await bridge.toggleRecording()
      const next = await bridge.getState()
      setState(next)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not toggle recording')
    }
  }

  return (
    <div>
      <PageHeader
        title="Recording"
        description={
          runtimeLabel === 'Local bridge'
            ? 'Controls the already-running local Python dictation app through the Tauri bridge.'
            : 'Browser review uses the mock bridge. Run inside Tauri with the Python app running for real controls.'
        }
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          <Card className="ld-card-shadow">
            <CardContent className="flex flex-col items-center gap-5 p-8 text-center">
              {recordingDisabled ? (
                <Alert>
                  <AlertTitle>Backend not running</AlertTitle>
                  <AlertDescription>
                    {backendStatus.message} Check Help/About or the top bar to start the local Python backend.
                  </AlertDescription>
                </Alert>
              ) : null}
              <RecordButton
                state={state}
                onToggle={() => void toggleRecording()}
                disabled={recordingDisabled}
              />
              <div>
                <p className="font-medium">Click once to record, click again to stop.</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {runtimeLabel === 'Local bridge'
                    ? 'The Python app still owns audio capture, transcription, and paste behavior.'
                    : 'The mock flow transcribes after stop and keeps output clipboard-ready.'}
                </p>
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
