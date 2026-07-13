import { useEffect, useState, type ReactNode } from 'react'
import { Copy, Download, History, Settings, X } from 'lucide-react'
import { toast } from 'sonner'
import { listen } from '@tauri-apps/api/event'

import { useBridge } from '@/bridge/bridgeContext'
import type { HistoryEntry } from '@/bridge/types'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'
import { truncateText } from '@/lib/format'
import { formatTime } from '@/lib/time'
import { hideAppToTray, hideQuickPopoverWindow, showMainWindow } from '@/tauri/windowControls'

interface PopoverPlacementEvent {
  tail_x: number
}

export function QuickHistoryPopoverSurface() {
  const bridge = useBridge()
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [tailX, setTailX] = useState(340)

  useEffect(() => {
    let mounted = true
    void bridge.getHistory().then((next) => {
      if (mounted) setEntries(next)
    }).catch(() => {
      if (mounted) setEntries([])
    })
    return () => {
      mounted = false
    }
  }, [bridge])

  useEffect(() => {
    let unlisten: (() => void) | undefined
    let cancelled = false

    void listen<PopoverPlacementEvent>('local-dictation:popover-placement', ({ payload }) => {
      if (!cancelled) setTailX(payload.tail_x)
    }).then((nextUnlisten) => {
      if (cancelled) {
        nextUnlisten()
      } else {
        unlisten = nextUnlisten
      }
    }).catch(() => {
      // Browser/mock mode has no Tauri event bus.
    })

    return () => {
      cancelled = true
      unlisten?.()
    }
  }, [])

  async function copyTranscript(text: string) {
    await copyText(text)
    toast.success('Copied transcript')
  }

  async function openRoute(route: string) {
    await showMainWindow(route)
    await hideQuickPopoverWindow()
  }

  async function hideToTray() {
    await hideAppToTray()
  }

  async function closePopover() {
    await hideQuickPopoverWindow()
  }

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-transparent">
      <section className="absolute inset-x-0 top-0 bottom-3 rounded-2xl border border-border/80 bg-popover p-4 pb-3 text-popover-foreground shadow-[0_18px_44px_-28px_rgba(15,23,42,0.55)]">
        <div className="flex flex-col gap-2.5">
          {entries.slice(0, 3).map((entry) => (
            <div key={`${entry.created_at}-${entry.text}`} className="grid grid-cols-[minmax(0,1fr)_34px] gap-3 border-b border-border/70 pb-2.5 last:border-b">
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground">{formatTime(entry.created_at)}</p>
                <p className="mt-0.5 line-clamp-2 text-[13px] leading-5">{truncateText(entry.text, 110)}</p>
              </div>
              <Button
                type="button"
                aria-label="Copy transcript"
                size="icon"
                variant="outline"
                className="size-8 self-center border-border/70 bg-background/60 text-muted-foreground shadow-none hover:bg-accent hover:text-accent-foreground"
                onClick={() => void copyTranscript(entry.text)}
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
          {entries.length === 0 ? (
            <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-border/70 text-sm text-muted-foreground">
              No recent transcripts yet
            </div>
          ) : null}
        </div>
        <div className="mt-3 grid grid-cols-[1fr_1fr_0.85fr_0.85fr] divide-x divide-border/70 border-t border-border/70 pt-2 text-xs">
          <FooterItem icon={<Settings />} label="Settings" onClick={() => void openRoute('settings')} />
          <FooterItem icon={<History />} label="History" onClick={() => void openRoute('history')} />
          <FooterItem icon={<Download />} label="Tray" onClick={() => void hideToTray()} />
          <FooterItem icon={<X />} label="Close" onClick={() => void closePopover()} />
        </div>
        <div
          className="absolute -bottom-[9px] size-5 rotate-45 rounded-[4px] border-b border-r border-border/80 bg-popover shadow-[6px_6px_12px_-10px_rgba(15,23,42,0.55)]"
          style={{ left: `${tailX - 10}px` }}
        />
        <div
          className="absolute -bottom-[5px] size-4 rotate-45 bg-popover"
          style={{ left: `${tailX - 8}px` }}
        />
      </section>
    </main>
  )
}

function FooterItem({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex min-w-0 items-center justify-center gap-1.5 px-1.5 py-1.5 text-muted-foreground transition hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="[&_svg]:size-3.5">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  )
}
