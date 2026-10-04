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
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#6250C8] text-white shadow-sm">
          <img src="/branding/icon-white.svg" alt="" className="h-8 w-8" draggable={false} />
        </div>
        <div>
          <p className="text-sm font-semibold leading-none">Local Dictation</p>
          <p className="mt-1 text-xs text-muted-foreground">Offline voice typing</p>
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
              aria-current={active ? 'page' : undefined}
            >
              <Icon className="h-4 w-4" strokeWidth={1.85} />
              {route.label}
            </Button>
          )
        })}
      </nav>

      <div className="mt-auto rounded-xl border border-border/70 bg-background/70 p-3 text-xs text-muted-foreground">
        <p className="font-medium text-foreground">Local Dictation</p>
        <p className="mt-1 leading-5">Offline speech recognition. Browser preview uses simulated data.</p>
      </div>
    </aside>
  )
}
