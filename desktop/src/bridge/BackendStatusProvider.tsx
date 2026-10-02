import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { watchCurrentWindowVisibility } from '@/tauri/windowControls'

import { isTauriRuntime } from '@/bridge'
import { BackendStatusContext } from '@/bridge/BackendStatusContext'
import { useBridge } from '@/bridge/bridgeContext'
import type { BackendStatus } from '@/bridge/types'

const fallbackLogPath = 'C:\\local-dictation\\dictation_debug.log'

function errorStatus(error: unknown): BackendStatus {
  return {
    status: 'error',
    owned: false,
    message: error instanceof Error ? error.message : 'Backend status unavailable.',
    log_path: fallbackLogPath,
  }
}

function transitionalStatus(status: BackendStatus['status'], message: string, current: BackendStatus | null): BackendStatus {
  return {
    status,
    owned: current?.owned ?? false,
    message,
    log_path: current?.log_path ?? fallbackLogPath,
    health: current?.health,
    launch_kind: current?.launch_kind,
    starting_seconds: current?.starting_seconds,
    last_error: current?.last_error,
  }
}

function nextPollDelay(status: BackendStatus | null, active: boolean): number | null {
  if (!active) return null
  if (!status) return 1000
  if (status.status === 'starting' || status.status === 'stopping') return 1000
  return 5000
}

export function BackendStatusProvider({
  children,
  autoStartInTauri = isTauriRuntime(),
}: {
  children: ReactNode
  autoStartInTauri?: boolean
}) {
  const bridge = useBridge()
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null)
  const autoStartAttempted = useRef(false)
  const statusVersion = useRef(0)
  const statusRead = useRef<Promise<BackendStatus> | null>(null)
  const operation = useRef<Promise<BackendStatus> | null>(null)
  const mounted = useRef(true)
  const pollingActive = autoStartInTauri || isTauriRuntime()

  const refreshBackendStatus = useCallback(async () => {
    if (operation.current) return operation.current.catch(errorStatus)
    if (statusRead.current) return statusRead.current
    statusRead.current = (async () => {
      for (;;) {
        if (operation.current) return operation.current.catch(errorStatus)
        const version = statusVersion.current
        const next = await bridge.getBackendStatus().catch(errorStatus)
        if (!mounted.current) return next
        if (version !== statusVersion.current) continue
        setBackendStatus(next)
        return next
      }
    })().finally(() => { statusRead.current = null })
    return statusRead.current
  }, [bridge])

  const runOperation = useCallback((action: () => Promise<BackendStatus>, status: BackendStatus['status'], message: string) => {
    if (operation.current) return Promise.reject(new Error('A backend operation is already in progress.'))
    statusVersion.current += 1
    setBackendStatus((current) => transitionalStatus(status, message, current))
    operation.current = Promise.resolve().then(action).then((next) => {
      setBackendStatus(next)
      return next
    }).catch((error: unknown) => {
      setBackendStatus(errorStatus(error))
      throw error
    }).finally(() => { statusVersion.current += 1; operation.current = null })
    return operation.current
  }, [])

  const startBackend = useCallback(() => runOperation(() => bridge.startBackend(), 'starting', 'Backend starting.'), [bridge, runOperation])
  const stopBackend = useCallback(() => runOperation(() => bridge.stopBackend(), 'stopping', 'Backend stopping.'), [bridge, runOperation])
  const restartBackend = useCallback(() => runOperation(() => bridge.restartBackend(), 'starting', 'Backend restarting.'), [bridge, runOperation])

  useEffect(() => {
    mounted.current = true
    let cancelled = false
    let timer: number | undefined
    let running = false
    let nativeVisible: boolean | undefined
    let visibilityVersion = 0
    let unlisten: (() => void) | undefined
    const visible = () => nativeVisible ?? !document.hidden

    async function tick(initial = false) {
      if (cancelled || running || (!initial && !visible())) return
      running = true
      let next = await refreshBackendStatus()
      if (cancelled) { running = false; return }
      if (
        autoStartInTauri &&
        !autoStartAttempted.current &&
        next.status === 'not_running'
      ) {
        autoStartAttempted.current = true
        try {
          next = await startBackend()
        } catch (error) {
          next = errorStatus(error)
        }
      }

      const delay = nextPollDelay(next, pollingActive)
      running = false
      if (delay !== null && visible()) {
        timer = window.setTimeout(() => {
          void tick()
        }, delay)
      }
    }

    const refreshWhenVisible = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = undefined
      if (visible()) void tick()
    }
    document.addEventListener('visibilitychange', refreshWhenVisible)
    if (isTauriRuntime()) {
      void watchCurrentWindowVisibility((visible) => {
        visibilityVersion += 1
        nativeVisible = visible
        refreshWhenVisible()
      }).then(async (off) => {
        if (cancelled) { off(); return }
        unlisten = off
        try {
          const version = visibilityVersion
          const initial = await invoke<boolean>('current_window_visible')
          if (!cancelled && version === visibilityVersion && typeof initial === 'boolean') { nativeVisible = initial; refreshWhenVisible() }
        } catch { /* Keep DOM visibility if the native visibility read fails. */ }
      }).catch(() => undefined)
    }
    void tick(true)

    return () => {
      mounted.current = false
      cancelled = true
      statusVersion.current += 1
      if (timer !== undefined) window.clearTimeout(timer)
      unlisten?.()
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [autoStartInTauri, pollingActive, refreshBackendStatus, startBackend])

  const value = useMemo(
    () => ({
      backendStatus,
      refreshBackendStatus,
      startBackend,
      stopBackend,
      restartBackend,
    }),
    [backendStatus, refreshBackendStatus, restartBackend, startBackend, stopBackend],
  )

  return <BackendStatusContext.Provider value={value}>{children}</BackendStatusContext.Provider>
}
