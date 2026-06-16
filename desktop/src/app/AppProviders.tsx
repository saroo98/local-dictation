import type { ReactNode } from 'react'
import { Toaster } from 'sonner'

import { BridgeContext } from '@/bridge/bridgeContext'
import { getBridge } from '@/bridge'
import { ThemeProvider } from '@/theme/theme-provider'

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <BridgeContext.Provider value={getBridge()}>
      <ThemeProvider>
        {children}
        <Toaster richColors closeButton position="bottom-right" />
      </ThemeProvider>
    </BridgeContext.Provider>
  )
}
