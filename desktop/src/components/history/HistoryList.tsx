import type { HistoryEntry } from '@/bridge/types'
import { HistoryRow } from '@/components/history/HistoryRow'

export function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  return (
    <div className="space-y-3">
      {entries.map((entry) => (
        <HistoryRow key={`${entry.created_at}-${entry.text}`} entry={entry} />
      ))}
    </div>
  )
}
