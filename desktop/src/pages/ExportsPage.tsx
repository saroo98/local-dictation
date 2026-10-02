import { toast } from 'sonner'
import { useRef, useState } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { useRuntimeState } from '@/bridge/useRuntimeState'

export function ExportsPage() {
  const bridge = useBridge()
  const { state, backendReady } = useRuntimeState()
  const [path, setPath] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const exporting = useRef(false)
  const disabled = pending || !backendReady || state?.connected === false

  async function exportAll(format: 'txt' | 'md') {
    if (exporting.current || disabled) return
    exporting.current = true
    setPending(true)
    try {
      const path = await bridge.exportHistory(format)
      setPath(path)
      toast.success(`Exported to ${path}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not export ${format.toUpperCase()}`)
    } finally { exporting.current = false; setPending(false) }
  }

  return (
    <div>
      <PageHeader title="Exports" description="Export recent local transcripts through the active bridge." />
      <div className="mb-5 flex gap-3">
        <Button type="button" disabled={disabled} onClick={() => void exportAll('txt')}>
          Export all TXT
        </Button>
        <Button type="button" disabled={disabled} variant="outline" onClick={() => void exportAll('md')}>
          Export all MD
        </Button>
      </div>
      {path ? <p role="status" className="break-all text-sm text-muted-foreground">Last export: {path}</p> : <p className="text-sm text-muted-foreground">Export the recent transcript history as TXT or Markdown. Choose the destination in Settings.</p>}
    </div>
  )
}
