import { Play } from 'lucide-react'

import type { HistoryEntry } from '@/bridge/types'
import { QuickHistoryPopoverPreview } from '@/components/dictation/QuickHistoryPopoverPreview'

export function BubblePreview({ entries }: { entries: HistoryEntry[] }) {
  return (
    <div className="flex flex-col items-end gap-4 rounded-[var(--radius)] border border-border/70 bg-card/70 p-5">
      <QuickHistoryPopoverPreview entries={entries} />
      <div className="mr-3 grid h-11 w-11 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg">
        <Play className="ml-0.5 h-5 w-5 fill-current" strokeWidth={1.8} />
      </div>
    </div>
  )
}
