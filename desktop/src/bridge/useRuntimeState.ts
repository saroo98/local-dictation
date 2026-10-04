import { useContext, useEffect, useState } from 'react'

import { BackendStatusContext } from '@/bridge/BackendStatusContext'
import { useBridge } from '@/bridge/bridgeContext'
import type { AppState } from '@/bridge/types'

export function useRuntimeState() {
  const bridge = useBridge()
  const backend = useContext(BackendStatusContext)
  const backendReady = !backend || backend.backendStatus?.status === 'ready'
  const [state, setState] = useState<AppState | null>(null)

  useEffect(() => {
    if (!backendReady) return
    let cancelled = false
    let received = false
    const off = bridge.onState((next) => {
      if (!cancelled) { received = true; setState(next) }
    })
    void bridge.getState().then((next) => {
      if (!cancelled && !received) setState(next)
    }).catch((error: unknown) => {
      if (!cancelled && !received) setState((current) => ({
        recording: false, transcribing: false, waiting_for_target_click: false,
        status: 'idle', latestTranscript: '', activeModel: '', activeLanguage: '',
        ...current, connected: false, connection_error: error instanceof Error ? error.message : 'Backend disconnected.',
      }))
    })
    return () => { cancelled = true; off() }
  }, [backendReady, bridge])

  const visibleState = backendReady || !state ? state : {
    ...state,
    connected: false,
    connection_error: backend?.backendStatus?.message ?? 'Backend unavailable.',
  }
  return { state: visibleState, backendReady, backendStatus: backend?.backendStatus ?? null }
}
