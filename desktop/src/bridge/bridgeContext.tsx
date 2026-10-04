import { createContext, useContext } from 'react'

import type { Bridge } from '@/bridge/types'

export const BridgeContext = createContext<Bridge | null>(null)

export function useBridge(): Bridge {
  const bridge = useContext(BridgeContext)
  if (!bridge) {
    throw new Error('useBridge must be used inside BridgeContext.Provider')
  }
  return bridge
}
