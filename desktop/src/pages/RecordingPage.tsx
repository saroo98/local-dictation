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
  const isBrowserMockBackend = backendStatus?.health?.backend_owner === 'browser-mock'
  const isLocalBridge = runtimeLabel === 'Local bridge' || (backendStatus !== null && !isBrowserMockBackend)
  const canReadRuntimeState = !isLocalBridge || backendReady
  const showBackendAlert = isLocalBridge && backendStatus !== null && !backendReady
  const recordingDisabled = isLocalBridge && !backendReady

  useEffect(() => {
    let mounted = true
    if (!canReadRuntimeState) {
      return () => {
        mounted = false
      }
    }
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
  }, [bridge, canReadRuntimeState])

  async function toggleRecording() {
    try {
      await bridge.toggleRecording()
      const next = await bridge.getState()
      setState(next)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not toggle recording')
    }
  }

  const backendAlertTitle =
    backendStatus?.status === 'starting'
      ? 'Backend starting'
      : backendStatus?.status === 'stopping'
        ? 'Backend stopping'
        : backendStatus?.status === 'error' || backendStatus?.status === 'unhealthy'
          ? 'Backend error'
          : 'Backend not running'

  const backendAlertDescription =
    backendStatus?.status === 'starting'
      ? `${backendStatus.message} You can keep using the rest of the app while it loads.`
      : `${backendStatus?.message ?? 'Backend not running.'} Check Help/About or the top bar to start the local Python backend.`
  const displayState = canReadRuntimeState ? state : null
  const displayHistory = canReadRuntimeState ? history : []

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
              {showBackendAlert ? (
                <Alert>
                  <AlertTitle>{backendAlertTitle}</AlertTitle>
                  <AlertDescription>{backendAlertDescription}</AlertDescription>
                </Alert>
              ) : null}
              <RecordButton
                state={displayState}
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
          <RecordingStatusCard state={displayState} />
          <TranscriptPreview text={displayState?.latestTranscript ?? ''} onOpenHistory={() => undefined} />
        </div>
        <div>
          <p className="mb-3 text-sm font-medium text-muted-foreground">Floating bubble and transcript popover preview</p>
          <BubblePreview entries={displayHistory} />
        </div>
      </div>
    </div>
  )
}
