import { useMemo, useState } from 'react'

import { routes, type RouteId } from '@/app/routes'

export function useAppNavigation() {
  const [activeRouteId, setActiveRouteId] = useState<RouteId>('recording')
  const activeRoute = useMemo(() => routes.find((route) => route.id === activeRouteId) ?? routes[0], [activeRouteId])

  return { activeRoute, activeRouteId, setActiveRouteId, routes }
}
