import { AppProviders } from '@/app/AppProviders'
import { DesktopApp } from '@/app/DesktopApp'

export default function App() {
  return (
    <AppProviders>
      <DesktopApp />
    </AppProviders>
  )
}
