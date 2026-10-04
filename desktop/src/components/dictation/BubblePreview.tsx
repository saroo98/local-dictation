import type { HistoryEntry } from '@/bridge/types'
import { QuickHistoryPopoverPreview } from '@/components/dictation/QuickHistoryPopoverPreview'

export function BubblePreview({ entries }: { entries: HistoryEntry[] }) {
  return (
    <div className="flex flex-col items-end gap-2 rounded-[var(--radius)] border border-border/70 bg-card/70 p-5">
      <QuickHistoryPopoverPreview entries={entries} />
      <div className="mr-3 grid h-11 w-11 place-items-center rounded-full bg-[#6250C8] text-white shadow-lg">
        <img src="/branding/icon-white.svg" alt="" className="h-7 w-7" draggable={false} />
      </div>
    </div>
  )
}
