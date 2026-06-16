import { Copy } from 'lucide-react'
import { toast } from 'sonner'

import type { HistoryEntry } from '@/bridge/types'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/clipboard'
import { formatTime } from '@/lib/time'

export function HistoryRow({ entry }: { entry: HistoryEntry }) {
  return (
    <div className="grid grid-cols-[92px_1fr_auto] items-start gap-4 rounded-xl border border-border/70 bg-card p-4">
      <p className="text-sm text-muted-foreground">{formatTime(entry.created_at)}</p>
      <p className="text-sm leading-6">{entry.text}</p>
      <Button
        type="button"
        aria-label="Copy transcript"
        variant="outline"
        size="icon"
        onClick={() => {
          void copyText(entry.text)
          toast.success('Copied transcript')
        }}
      >
        <Copy className="h-4 w-4" />
      </Button>
    </div>
  )
}
