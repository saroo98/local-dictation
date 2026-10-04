import type { ReactNode } from 'react'

import type { useAppNavigation } from '@/app/useAppNavigation'
import { Sidebar } from '@/components/shell/Sidebar'
import { TopBar } from '@/components/shell/TopBar'

interface AppShellProps {
  children: ReactNode
  navigation: ReturnType<typeof useAppNavigation>
}

export function AppShell({ children, navigation }: AppShellProps) {
  return (
    <div className="grid min-h-screen ld-shell-grid bg-background text-foreground">
      <Sidebar navigation={navigation} />
      <main className="min-w-0 border-l border-border/70">
        <TopBar title={navigation.activeRoute.title} />
        <div className="mx-auto max-w-6xl px-6 py-5">{children}</div>
      </main>
    </div>
  )
}
