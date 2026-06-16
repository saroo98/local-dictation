import { useCallback, useEffect, useState } from 'react'

import { isTauriRuntime } from '@/bridge'
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

function nextPollDelay(status: BackendStatus | null): number | null {
  if (!isTauriRuntime()) return null
  if (!status) return 1000
  if (status.status === 'starting' || status.status === 'stopping') return 1000
  if (status.status === 'ready') return 5000
  return 5000
}

export function useBackendStatus() {
  const bridge = useBridge()
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null)

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
    setBackendStatus((current) => ({
      status: 'starting',
      owned: current?.owned ?? false,
      message: 'Backend starting.',
      log_path: current?.log_path ?? fallbackLogPath,
      health: current?.health,
    }))
    const next = await bridge.startBackend()
    setBackendStatus(next)
    return next
  }, [bridge])

  const stopBackend = useCallback(async () => {
    setBackendStatus((current) => ({
      status: 'stopping',
      owned: current?.owned ?? false,
      message: 'Backend stopping.',
      log_path: current?.log_path ?? fallbackLogPath,
      health: current?.health,
    }))
    const next = await bridge.stopBackend()
    setBackendStatus(next)
    return next
  }, [bridge])

  const restartBackend = useCallback(async () => {
    setBackendStatus((current) => ({
      status: 'starting',
      owned: current?.owned ?? false,
      message: 'Backend restarting.',
      log_path: current?.log_path ?? fallbackLogPath,
      health: current?.health,
    }))
    const next = await bridge.restartBackend()
    setBackendStatus(next)
    return next
  }, [bridge])

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function tick() {
      const next = await refreshBackendStatus()
      if (cancelled) return
      const delay = nextPollDelay(next)
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
  }, [refreshBackendStatus])

  return {
    backendStatus,
    refreshBackendStatus,
    startBackend,
    stopBackend,
    restartBackend,
  }
}
