import { createContext } from 'react'

import type { BackendStatus } from '@/bridge/types'

export interface BackendStatusContextValue {
  backendStatus: BackendStatus | null
  refreshBackendStatus: () => Promise<BackendStatus>
  startBackend: () => Promise<BackendStatus>
  stopBackend: () => Promise<BackendStatus>
  restartBackend: () => Promise<BackendStatus>
}

export const BackendStatusContext = createContext<BackendStatusContextValue | null>(null)
