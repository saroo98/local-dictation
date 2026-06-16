import { Copy, History, Settings, X } from 'lucide-react'
import { toast } from 'sonner'

import type { HistoryEntry } from '@/bridge/types'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'
import { truncateText } from '@/lib/format'
import { formatTime } from '@/lib/time'

export function QuickHistoryPopoverPreview({ entries }: { entries: HistoryEntry[] }) {
  return (
    <div className="relative w-[360px] rounded-2xl border border-border bg-popover p-4 text-popover-foreground shadow-2xl">
      <div className="space-y-3">
        {entries.slice(0, 3).map((entry) => (
          <div key={`${entry.created_at}-${entry.text}`} className="grid grid-cols-[1fr_40px] gap-3 border-b border-border/70 pb-3 last:border-b">
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">{formatTime(entry.created_at)}</p>
              <p className="mt-1 text-sm leading-5">{truncateText(entry.text, 86)}</p>
            </div>
            <Button
              type="button"
              aria-label="Copy transcript"
              size="icon"
              variant="outline"
              className="self-center"
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
      <div className="mt-3 grid grid-cols-3 divide-x divide-border/80 text-sm">
        <FooterItem icon={<Settings className="h-4 w-4" />} label="Settings" />
        <FooterItem icon={<History className="h-4 w-4" />} label="History" />
        <FooterItem icon={<X className="h-4 w-4" />} label="Close app" />
      </div>
      <div className="absolute -bottom-3 right-7 h-6 w-6 rotate-45 border-b border-r border-border bg-popover" />
    </div>
  )
}

function FooterItem({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button type="button" className="flex items-center justify-center gap-2 px-2 py-2 text-muted-foreground transition hover:text-foreground">
      {icon}
      {label}
    </button>
  )
}
