import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function HelpAboutPage() {
  const bridge = useBridge()
  const { backendStatus, startBackend, stopBackend, restartBackend } = useBackendStatus()
  const [checked, setChecked] = useState(false)
  const isBrowserMock = backendStatus?.health?.backend_owner === 'browser-mock'

  async function checkUpdates() {
    try {
      await bridge.checkForUpdates()
      setChecked(true)
      toast.info('Mock update check only')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Update check is unavailable.')
    }
  }

  async function runBackendAction(action: 'start' | 'restart' | 'stop') {
    try {
      if (action === 'start') {
        await startBackend()
        toast.success('Backend start requested')
      } else if (action === 'restart') {
        await restartBackend()
        toast.success('Backend restart requested')
      } else {
        await stopBackend()
        toast.success('Backend stop requested')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Backend action failed.')
    }
  }

  return (
    <div>
      <PageHeader title="Help/About" description="Project context, privacy posture, and migration notes." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" /> Local-first by design
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <p>No cloud transcription, telemetry, analytics, CDN fonts, or automatic network calls are included.</p>
            <p>Stage 4 can start and monitor the local Python backend in development Tauri builds.</p>
            <p>Browser mode remains mock-backed. Real backend start/stop controls require the Tauri runtime.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Backend</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="rounded-lg border border-border bg-secondary/40 p-3">
              <p className="font-medium">{backendStatus?.message ?? 'Checking backend status.'}</p>
              <dl className="mt-3 grid gap-2 text-muted-foreground sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase tracking-wide">Status</dt>
                  <dd>{backendStatus?.status ?? 'checking'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide">Owner</dt>
                  <dd>{backendStatus?.health?.backend_owner ?? 'unknown'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide">Model</dt>
                  <dd>{backendStatus?.health?.model ?? 'unknown'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide">Device</dt>
                  <dd>{backendStatus?.health?.device ?? 'unknown'}</dd>
                </div>
              </dl>
              <p className="mt-3 break-all text-xs text-muted-foreground">Log: {backendStatus?.log_path ?? 'C:\\local-dictation\\dictation_debug.log'}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" disabled={isBrowserMock} onClick={() => void runBackendAction('start')}>
                Start backend
              </Button>
              <Button type="button" variant="outline" disabled={isBrowserMock} onClick={() => void runBackendAction('restart')}>
                Restart backend
              </Button>
              <Button type="button" variant="outline" disabled={isBrowserMock} onClick={() => void runBackendAction('stop')}>
                Stop backend
              </Button>
            </div>
            {isBrowserMock ? <p className="text-xs text-muted-foreground">Backend process controls require the Tauri runtime.</p> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Version</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">0.4.0-backend-manager</p>
            <Button type="button" variant="outline" onClick={() => void checkUpdates()}>
              Check for updates
            </Button>
            {checked ? <p className="text-sm text-primary">Mock update check complete.</p> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
