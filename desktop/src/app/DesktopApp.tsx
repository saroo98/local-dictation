import { AppShell } from '@/components/shell/AppShell'
import { useAppNavigation } from '@/app/useAppNavigation'

export function DesktopApp() {
  const navigation = useAppNavigation()
  const Page = navigation.activeRoute.component

  return (
    <AppShell navigation={navigation}>
      <Page />
    </AppShell>
  )
}
