import { AudioLines } from 'lucide-react'

import type { useAppNavigation } from '@/app/useAppNavigation'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'

interface SidebarProps {
  navigation: ReturnType<typeof useAppNavigation>
}

export function Sidebar({ navigation }: SidebarProps) {
  return (
    <aside className="flex min-h-screen flex-col bg-card/80 px-4 py-5 backdrop-blur">
      <div className="mb-7 flex items-center gap-3 px-2">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
          <AudioLines className="h-5 w-5" strokeWidth={1.8} />
        </div>
        <div>
          <p className="text-sm font-semibold leading-none">Local Dictation</p>
          <p className="mt-1 text-xs text-muted-foreground">Mock desktop UI</p>
        </div>
      </div>

      <nav className="space-y-1" aria-label="Main navigation">
        {navigation.routes.map((route) => {
          const Icon = route.icon
          const active = route.id === navigation.activeRouteId
          return (
            <Button
              key={route.id}
              type="button"
              variant="ghost"
              className={cn(
                'h-10 w-full justify-start rounded-xl px-3 text-sm',
                active && 'bg-secondary text-foreground shadow-sm',
              )}
              onClick={() => navigation.setActiveRouteId(route.id)}
            >
              <Icon className="h-4 w-4" strokeWidth={1.85} />
              {route.label}
            </Button>
          )
        })}
      </nav>

      <div className="mt-auto rounded-xl border border-border/70 bg-background/70 p-3 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Phase 1</p>
        <p className="mt-1 leading-5">Reviewable UI only. No microphone, model, filesystem, or Python backend calls.</p>
      </div>
    </aside>
  )
}
