import { useEffect, useRef } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import { isTauriWindowRuntime, showBubbleWindow } from '@/tauri/windowControls'

export function TauriBubbleController() {
  const bridge = useBridge()
  const { backendStatus } = useBackendStatus()
  const ready = backendStatus?.status === 'ready'
  const restored = useRef(false)

  useEffect(() => {
    if (!isTauriWindowRuntime() || !ready || restored.current) return
    let cancelled = false
    let timer: number | undefined
    async function restore() {
      try {
        const settings = await bridge.getSettings()
        if (cancelled) return
        await showBubbleWindow(settings.bubble_position)
        if (!cancelled) restored.current = true
      } catch {
        if (!cancelled) timer = window.setTimeout(() => { void restore() }, 1000)
      }
    }
    void restore()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [bridge, ready])

  return null
}
