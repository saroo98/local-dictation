import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import type { HistoryEntry } from '@/bridge/types'
import { EmptyHistory } from '@/components/history/EmptyHistory'
import { HistoryList } from '@/components/history/HistoryList'
import { HistorySearch } from '@/components/history/HistorySearch'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'

export function HistoryPage() {
  const bridge = useBridge()
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    void bridge.getHistory().then(setEntries).catch(() => setEntries([]))
  }, [bridge])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return entries
    return entries.filter((entry) => entry.text.toLowerCase().includes(normalized))
  }, [entries, query])

  async function clearHistory() {
    try {
      await bridge.clearHistory()
      setEntries(await bridge.getHistory())
      toast.success('History cleared')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not clear history')
    }
  }

  async function exportHistory(format: 'txt' | 'md') {
    try {
      const path = await bridge.exportHistory(format)
      toast.success(`Exported to ${path}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not export ${format.toUpperCase()}`)
    }
  }

  return (
    <div>
      <PageHeader title="History" description="Recent local transcripts with fast copy actions and export entry points." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="min-w-72 flex-1">
          <HistorySearch value={query} onChange={setQuery} />
        </div>
        <Button type="button" variant="outline" onClick={() => void exportHistory('txt')}>
          Export TXT
        </Button>
        <Button type="button" variant="outline" onClick={() => void exportHistory('md')}>
          Export MD
        </Button>
        <Button type="button" variant="ghost" onClick={() => void clearHistory()}>
          Clear
        </Button>
      </div>
      {filtered.length ? <HistoryList entries={filtered} /> : <EmptyHistory />}
    </div>
  )
}
