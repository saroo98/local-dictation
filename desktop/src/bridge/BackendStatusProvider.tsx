import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

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
  const pollingActive = autoStartInTauri || isTauriRuntime()

  const refreshBackendStatus = useCallback(async () => {
    try {
      const next = await bridge.getBackendStatus()
      setBackendStatus(next)
      return next
    } catch (error) {
      const next = errorStatus(error)
      setBackendStatus(next)
      return next
    }
  }, [bridge])

  const startBackend = useCallback(async () => {
    setBackendStatus((current) => transitionalStatus('starting', 'Backend starting.', current))
    const next = await bridge.startBackend()
    setBackendStatus(next)
    return next
  }, [bridge])

  const stopBackend = useCallback(async () => {
    setBackendStatus((current) => transitionalStatus('stopping', 'Backend stopping.', current))
    const next = await bridge.stopBackend()
    setBackendStatus(next)
    return next
  }, [bridge])

  const restartBackend = useCallback(async () => {
    setBackendStatus((current) => transitionalStatus('starting', 'Backend restarting.', current))
    const next = await bridge.restartBackend()
    setBackendStatus(next)
    return next
  }, [bridge])

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function tick() {
      let next = await refreshBackendStatus()
      if (cancelled) return
      if (
        autoStartInTauri &&
        !autoStartAttempted.current &&
        next.status === 'not_running'
      ) {
        autoStartAttempted.current = true
        try {
          next = await startBackend()
        } catch {
          // The explicit backend status poll will surface the error message.
        }
      }

      const delay = nextPollDelay(next, pollingActive)
      if (delay !== null) {
        timer = window.setTimeout(() => {
          void tick()
        }, delay)
      }
    }

    void tick()

    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
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
