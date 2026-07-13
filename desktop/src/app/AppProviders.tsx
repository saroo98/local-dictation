import type { ReactNode } from 'react'
import { Toaster } from 'sonner'

import { BridgeContext } from '@/bridge/bridgeContext'
import { getBridge } from '@/bridge'
import { BackendStatusProvider } from '@/bridge/BackendStatusProvider'
import { ThemeProvider } from '@/theme/theme-provider'

export function AppProviders({
  children,
  backendStatusEnabled = true,
}: {
  children: ReactNode
  backendStatusEnabled?: boolean
}) {
  return (
    <BridgeContext.Provider value={getBridge()}>
      <ThemeProvider>
        {backendStatusEnabled ? <BackendStatusProvider>{children}</BackendStatusProvider> : children}
        <Toaster richColors closeButton position="bottom-right" />
      </ThemeProvider>
    </BridgeContext.Provider>
  )
}
