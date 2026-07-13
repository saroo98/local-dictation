import type { ReactNode } from 'react'
import { Copy, Download, History, Settings, X } from 'lucide-react'
import { toast } from 'sonner'

import type { HistoryEntry } from '@/bridge/types'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'
import { truncateText } from '@/lib/format'
import { formatTime } from '@/lib/time'

export function QuickHistoryPopoverPreview({ entries }: { entries: HistoryEntry[] }) {
  return (
    <div className="relative w-[390px] rounded-2xl border border-border bg-popover p-4 pb-3 text-popover-foreground shadow-[0_18px_44px_-28px_rgba(15,23,42,0.55)]">
      <div className="flex flex-col gap-2.5">
        {entries.slice(0, 3).map((entry) => (
          <div key={`${entry.created_at}-${entry.text}`} className="grid grid-cols-[1fr_34px] gap-3 border-b border-border/70 pb-2.5 last:border-b">
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">{formatTime(entry.created_at)}</p>
              <p className="mt-0.5 line-clamp-2 text-[13px] leading-5">{truncateText(entry.text, 98)}</p>
            </div>
            <Button
              type="button"
              aria-label="Copy transcript"
              size="icon"
              variant="outline"
              className="size-8 self-center border-border/70 bg-background/60 text-muted-foreground shadow-none hover:bg-accent hover:text-foreground"
              onClick={() => {
                void copyText(entry.text)
                toast.success('Copied transcript')
              }}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-[1fr_1fr_0.85fr_0.85fr] divide-x divide-border/70 border-t border-border/70 pt-2 text-xs">
        <FooterItem icon={<Settings />} label="Settings" />
        <FooterItem icon={<History />} label="History" />
        <FooterItem icon={<Download />} label="Tray" />
        <FooterItem icon={<X />} label="Close" />
      </div>
      <div className="absolute -bottom-[9px] right-7 size-5 rotate-45 rounded-[4px] border-b border-r border-border bg-popover shadow-[6px_6px_12px_-10px_rgba(15,23,42,0.55)]" />
      <div className="absolute -bottom-[5px] right-[31px] size-4 rotate-45 bg-popover" />
    </div>
  )
}

function FooterItem({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <button type="button" className="flex min-w-0 items-center justify-center gap-1.5 px-1.5 py-1.5 text-muted-foreground transition hover:text-foreground">
      <span className="[&_svg]:size-3.5">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  )
}
