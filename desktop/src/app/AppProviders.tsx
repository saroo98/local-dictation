import type { ReactNode } from 'react'
import { Toaster } from 'sonner'

import { BridgeContext } from '@/bridge/bridgeContext'
import { getBridge } from '@/bridge'
import { BackendStatusProvider } from '@/bridge/BackendStatusProvider'
import { ThemeProvider } from '@/theme/theme-provider'
import { useTheme } from '@/theme/use-theme'

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
        <AppearanceToaster />
      </ThemeProvider>
    </BridgeContext.Provider>
  )
}

function AppearanceToaster() {
  const { resolvedMode } = useTheme()
  return <Toaster theme={resolvedMode} richColors closeButton position="bottom-right" />
}
