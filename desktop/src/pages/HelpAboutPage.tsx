import { ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { getVersion } from '@tauri-apps/api/app'

import { useBridge } from '@/bridge/bridgeContext'
import { isTauriRuntime } from '@/bridge'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import { useRuntimeState } from '@/bridge/useRuntimeState'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function HelpAboutPage() {
  const bridge = useBridge()
  const { backendStatus, startBackend, stopBackend, restartBackend } = useBackendStatus()
  const { state } = useRuntimeState()
  const [version, setVersion] = useState(isTauriRuntime() ? 'Reading app version...' : 'Browser preview')
  const [pending, setPending] = useState(false)
  const actionPending = useRef(false)
  const isBrowserMock = backendStatus?.health?.backend_owner === 'browser-mock'
  const backendBusy = pending || backendStatus?.status === 'starting' || backendStatus?.status === 'stopping'

  useEffect(() => {
    if (!isTauriRuntime()) return
    let cancelled = false
    void getVersion().then((next) => { if (!cancelled) setVersion(next) })
      .catch(() => { if (!cancelled) setVersion('App version unavailable') })
    return () => { cancelled = true }
  }, [])

  async function runBackendAction(action: 'start' | 'restart' | 'stop') {
    if (actionPending.current || backendBusy) return
    actionPending.current = true
    setPending(true)
    try {
      let next
      if (action === 'start') {
        next = await startBackend()
      } else if (action === 'restart') {
        next = await restartBackend()
      } else {
        next = await stopBackend()
      }
      if (next.status === 'error' || next.status === 'unhealthy') toast.error(next.message)
      else toast.success(next.message)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Backend action failed.')
    } finally { actionPending.current = false; setPending(false) }
  }

  async function retryResources() {
    if (actionPending.current) return
    actionPending.current = true
    setPending(true)
    try { await bridge.retryResources(); await bridge.getState() }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Could not retry recording resources') }
    finally { actionPending.current = false; setPending(false) }
  }

  return (
    <div>
      <PageHeader title="Help/About" description="Local recording, recovery, and app information." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" /> Local-first by design
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <p>Speech is transcribed on your device. Models and transcript history stay local. Explicit model downloads use the network.</p>
            <p>The native app starts the packaged local backend. Debug builds can use the repository Python environment.</p>
            <p>Browser mode remains mock-backed. Real backend start/stop controls require the Tauri runtime.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Backend</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="rounded-lg border border-border bg-secondary/40 p-3">
              <p role="status" aria-live="polite" className="font-medium">{backendStatus?.message ?? 'Checking backend status.'}</p>
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
            {state?.error || state?.connected === false ? <p role="alert" className="text-destructive">{state.connection_error || state.error}</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button type="button" disabled={isBrowserMock || backendBusy || backendStatus?.status === 'ready'} onClick={() => void runBackendAction('start')}>
                Start backend
              </Button>
              <Button type="button" variant="outline" disabled={isBrowserMock || backendBusy || !backendStatus?.owned} onClick={() => void runBackendAction('restart')}>
                Restart backend
              </Button>
              <Button type="button" variant="outline" disabled={isBrowserMock || backendBusy || !backendStatus?.owned} onClick={() => void runBackendAction('stop')}>
                Stop backend
              </Button>
              {backendStatus?.status === 'ready' ? <Button type="button" variant="outline" disabled={pending || Boolean(state?.loading || state?.recording || state?.transcribing) || state?.connected === false} onClick={() => void retryResources()}>Retry resources</Button> : null}
            </div>
            {isBrowserMock ? <p className="text-xs text-muted-foreground">Backend process controls require the Tauri runtime.</p> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Version</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <img src="/branding/logo-horizontal-color.svg" alt="Local Dictation" className="h-auto w-64 max-w-full dark:hidden" width={627} height={128} />
            <img src="/branding/logo-horizontal-white.svg" alt="Local Dictation" className="hidden h-auto w-64 max-w-full dark:block" width={627} height={128} />
            <p className="text-sm text-muted-foreground">{version}</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
