import { useEffect } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
import { isTauriWindowRuntime, showBubbleWindow } from '@/tauri/windowControls'

export function TauriBubbleController() {
  const bridge = useBridge()

  useEffect(() => {
    if (!isTauriWindowRuntime()) return
    let cancelled = false
    void bridge.getSettings().then((settings) => {
      if (!cancelled) {
        void showBubbleWindow(settings.bubble_position)
      }
    }).catch(() => {
      if (!cancelled) void showBubbleWindow(null)
    })
    return () => {
      cancelled = true
    }
  }, [bridge])

  return null
}
