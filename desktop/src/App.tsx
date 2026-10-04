import { useLayoutEffect } from 'react'

import { AppProviders } from '@/app/AppProviders'
import { DesktopApp } from '@/app/DesktopApp'
import { FloatingBubbleSurface } from '@/components/dictation/FloatingBubbleSurface'
import { QuickHistoryPopoverSurface } from '@/components/dictation/QuickHistoryPopoverSurface'
import { TauriBubbleController } from '@/components/dictation/TauriBubbleController'

type AppSurface = 'main' | 'bubble' | 'quick-popover'

function currentSurface(): AppSurface {
  const surface = new URLSearchParams(window.location.search).get('surface')
  if (surface === 'bubble' || surface === 'quick-popover') return surface
  return 'main'
}

export default function App() {
  const surface = currentSurface()

  useLayoutEffect(() => {
    document.documentElement.dataset.surface = surface
  }, [surface])

  return (
    <AppProviders backendStatusEnabled={surface === 'main'}>
      {surface === 'bubble' ? <FloatingBubbleSurface /> : null}
      {surface === 'quick-popover' ? <QuickHistoryPopoverSurface /> : null}
      {surface === 'main' ? (
        <>
          <TauriBubbleController />
          <DesktopApp />
        </>
      ) : null}
    </AppProviders>
  )
}
