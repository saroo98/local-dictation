import { useEffect, useMemo, useState } from 'react'
import { listen } from '@tauri-apps/api/event'

import { routes, type RouteId } from '@/app/routes'

export function useAppNavigation() {
  const [activeRouteId, setActiveRouteId] = useState<RouteId>('recording')
  const activeRoute = useMemo(() => routes.find((route) => route.id === activeRouteId) ?? routes[0], [activeRouteId])

  useEffect(() => {
    let cancelled = false
    let unlisten: (() => void) | undefined
    void listen<string>('local-dictation:navigate', (event) => {
      if (!cancelled && routes.some((route) => route.id === event.payload)) {
        setActiveRouteId(event.payload as RouteId)
      }
    }).then((off) => {
      if (cancelled) {
        off()
      } else {
        unlisten = off
      }
    }).catch(() => undefined)
    return () => {
      cancelled = true
      unlisten?.()
    }
  }, [])

  return { activeRoute, activeRouteId, setActiveRouteId, routes }
}
