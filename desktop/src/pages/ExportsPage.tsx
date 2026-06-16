import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import { ExportRow } from '@/components/exports/ExportRow'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { exportFixtures } from '@/fixtures/exports'

export function ExportsPage() {
  const bridge = useBridge()

  async function exportAll(format: 'txt' | 'md') {
    await bridge.exportHistory(format)
    toast.success(`Mock ${format.toUpperCase()} export prepared`)
  }

  return (
    <div>
      <PageHeader title="Exports" description="Export affordances for the future desktop app. Phase 1 uses mock data only." />
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
