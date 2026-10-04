import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { getBridgeRuntimeLabel } from '@/bridge'
import { useBridge } from '@/bridge/bridgeContext'
import { useRuntimeState } from '@/bridge/useRuntimeState'
import type { HistoryEntry } from '@/bridge/types'
import type { RouteId, RoutePageProps } from '@/app/routes'
import { BubblePreview } from '@/components/dictation/BubblePreview'
import { RecordButton } from '@/components/dictation/RecordButton'
import { RecordingStatusCard } from '@/components/dictation/RecordingStatusCard'
import { TranscriptPreview } from '@/components/dictation/TranscriptPreview'
import { PageHeader } from '@/components/shell/PageHeader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { showMainWindow } from '@/tauri/windowControls'

export function RecordingPage({ onNavigate }: RoutePageProps = {}) {
  const bridge = useBridge()
  const runtimeLabel = getBridgeRuntimeLabel()
  const { state, backendReady, backendStatus } = useRuntimeState()
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [pending, setPending] = useState(false)
  const actionPending = useRef(false)
  const isBrowserMockBackend = backendStatus?.health?.backend_owner === 'browser-mock'
  const isLocalBridge = runtimeLabel === 'Local bridge' || (backendStatus !== null && !isBrowserMockBackend)
  const canReadRuntimeState = !isLocalBridge || backendReady
  const showBackendAlert = isLocalBridge && backendStatus !== null && !backendReady
  const recordingDisabled = pending || !canReadRuntimeState
  const historyRevision = state?.history_revision ?? 0

  useEffect(() => {
    let mounted = true
    if (!canReadRuntimeState) {
      return () => {
        mounted = false
      }
    }
    void bridge
      .getHistory()
      .then((next) => {
        if (mounted) setHistory(next)
      })
      .catch(() => {
        // Preserve the latest successfully read preview during a transient failure.
      })
    return () => {
      mounted = false
    }
  }, [bridge, canReadRuntimeState, historyRevision])

  async function toggleRecording() {
    if (actionPending.current || recordingDisabled || state?.loading || state?.transcribing || state?.connected === false || state?.recording_ready === false) return
    actionPending.current = true
    setPending(true)
    try {
      await bridge.toggleRecording()
      await bridge.getState()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not toggle recording')
    } finally { actionPending.current = false; setPending(false) }
  }

  function navigate(route: RouteId) {
    if (onNavigate) onNavigate(route)
    else void showMainWindow(route).catch((error: unknown) => toast.error(error instanceof Error ? error.message : 'Could not open the app'))
  }

  async function retryResources() {
    if (actionPending.current) return
    actionPending.current = true
    setPending(true)
    try { await bridge.retryResources(); await bridge.getState() }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Could not retry recording resources') }
    finally { actionPending.current = false; setPending(false) }
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
      : `${backendStatus?.message ?? 'Backend not running.'} Open Help/About for backend recovery controls.`
  const displayState = state
  const displayHistory = history

  return (
    <div>
      <PageHeader
        title="Recording"
        description={
          runtimeLabel === 'Local bridge'
            ? 'Record and transcribe speech locally.'
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
              {displayState?.error || displayState?.connected === false || displayState?.recording_ready === false ? (
                <Alert>
                  <AlertTitle>{displayState?.connected === false ? 'Backend disconnected' : 'Recording needs attention'}</AlertTitle>
                  <AlertDescription>
                    {displayState.connection_error || displayState.error || 'Recording resources are unavailable. Check Models and your microphone settings.'}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {displayState.recording_ready === false ? <Button variant="outline" disabled={pending || Boolean(displayState.loading) || displayState.connected === false} onClick={() => void retryResources()}>Retry resources</Button> : null}
                      <Button variant="outline" onClick={() => navigate('models')}>Open Models</Button>
                      <Button variant="outline" onClick={() => navigate('settings')}>Open Settings</Button>
                    </div>
                  </AlertDescription>
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
                    ? 'When transcription is ready, click a writable target to paste the text.'
                    : 'The mock flow transcribes after stop and keeps output clipboard-ready.'}
                </p>
              </div>
            </CardContent>
          </Card>
          <RecordingStatusCard state={displayState} mock={!isLocalBridge} />
          <TranscriptPreview text={displayState?.latestTranscript ?? ''} onOpenHistory={() => navigate('history')} />
        </div>
        <div>
          <p className="mb-3 text-sm font-medium text-muted-foreground">Floating bubble and transcript popover preview</p>
          <BubblePreview entries={displayHistory} />
        </div>
      </div>
    </div>
  )
}
