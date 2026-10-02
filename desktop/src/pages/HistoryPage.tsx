import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { watchCurrentWindowVisibility } from '@/tauri/windowControls'

import { useBridge } from '@/bridge/bridgeContext'
import { useRuntimeState } from '@/bridge/useRuntimeState'
import type { HistoryEntry } from '@/bridge/types'
import { EmptyHistory } from '@/components/history/EmptyHistory'
import { HistoryList } from '@/components/history/HistoryList'
import { HistorySearch } from '@/components/history/HistorySearch'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'

export function HistoryPage() {
  const bridge = useBridge()
  const { state, backendReady } = useRuntimeState()
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [pending, setPending] = useState(false)
  const actionPending = useRef(false)
  const readId = useRef(0)
  const canRead = backendReady && state?.connected !== false
  const historyRevision = state?.history_revision ?? 0

  const refresh = useCallback(() => {
    const id = ++readId.current
    return bridge.getHistory().then((next) => {
      if (id === readId.current) { setEntries(next); setLoaded(true); setError(null) }
    }).catch((cause: unknown) => {
      if (id === readId.current) setError(cause instanceof Error ? cause.message : 'Could not load history')
    })
  }, [bridge])

  useEffect(() => {
    if (canRead) void refresh()
    return () => { readId.current += 1 }
  }, [canRead, historyRevision, refresh])

  useEffect(() => {
    if (!canRead) return
    let cancelled = false
    let unlisten: (() => void) | undefined
    const onVisible = () => { if (!document.hidden) void refresh() }
    document.addEventListener('visibilitychange', onVisible)
    void watchCurrentWindowVisibility((visible) => {
      if (!cancelled && visible) void refresh()
    }).then((off) => { if (cancelled) off(); else unlisten = off }).catch(() => undefined)
    return () => { cancelled = true; unlisten?.(); document.removeEventListener('visibilitychange', onVisible) }
  }, [canRead, refresh])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return entries
    return entries.filter((entry) => entry.text.toLowerCase().includes(normalized))
  }, [entries, query])

  async function clearHistory() {
    if (actionPending.current) return
    actionPending.current = true
    setPending(true)
    try {
      await bridge.clearHistory()
      await refresh()
      toast.success('History cleared')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not clear history')
    } finally { actionPending.current = false; setPending(false) }
  }

  async function exportHistory(format: 'txt' | 'md') {
    if (actionPending.current) return
    actionPending.current = true
    setPending(true)
    try {
      const path = await bridge.exportHistory(format)
      toast.success(`Exported to ${path}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not export ${format.toUpperCase()}`)
    } finally { actionPending.current = false; setPending(false) }
  }

  return (
    <div>
      <PageHeader title="History" description="Recent local transcripts with fast copy actions and export entry points." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="min-w-72 flex-1">
          <HistorySearch value={query} onChange={setQuery} />
        </div>
        <Button type="button" variant="outline" disabled={!canRead || pending} onClick={() => void exportHistory('txt')}>
          Export TXT
        </Button>
        <Button type="button" variant="outline" disabled={!canRead || pending} onClick={() => void exportHistory('md')}>
          Export MD
        </Button>
        <Button type="button" variant="ghost" disabled={!canRead || pending || (entries.length === 0 && !state?.history_error)} onClick={() => void clearHistory()}>
          Clear
        </Button>
      </div>
      {state?.history_error ? <p role="alert" className="mb-4 text-sm text-destructive">
        {state.history_error} Clear to recover an empty history. The unreadable file will be backed up first.
      </p> : null}
      {error || !canRead ? (
        <div role="alert" className="mb-4 flex items-center gap-3 text-sm">
          <p className="text-destructive">{error ?? state?.connection_error ?? 'Waiting for the backend...'}</p>
          <Button variant="outline" disabled={!canRead} onClick={() => void refresh()}>Retry history</Button>
        </div>
      ) : null}
      {filtered.length ? <HistoryList entries={filtered} /> : loaded && !error && canRead ? <EmptyHistory /> : !error ? <p className="text-sm text-muted-foreground">Loading history...</p> : null}
    </div>
  )
}
