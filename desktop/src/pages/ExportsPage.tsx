import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import { ExportRow } from '@/components/exports/ExportRow'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { exportFixtures } from '@/fixtures/exports'

export function ExportsPage() {
  const bridge = useBridge()

  async function exportAll(format: 'txt' | 'md') {
    try {
      const path = await bridge.exportHistory(format)
      toast.success(`Exported to ${path}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not export ${format.toUpperCase()}`)
    }
  }

  return (
    <div>
      <PageHeader title="Exports" description="Export recent local transcripts through the active bridge." />
      <div className="mb-5 flex gap-3">
        <Button type="button" onClick={() => void exportAll('txt')}>
          Export all TXT
        </Button>
        <Button type="button" variant="outline" onClick={() => void exportAll('md')}>
          Export all MD
        </Button>
      </div>
      <div className="space-y-3">
        {exportFixtures.map((item) => (
          <ExportRow key={item.name} name={item.name} createdAt={item.created_at} format={item.format} />
        ))}
      </div>
    </div>
  )
}
