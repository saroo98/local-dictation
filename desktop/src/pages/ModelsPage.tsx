import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import type { ModelInfo, ModelOrder } from '@/bridge/types'
import { AddCustomModelDialog } from '@/components/models/AddCustomModelDialog'
import { ModelCard } from '@/components/models/ModelCard'
import { ModelOrderToggle } from '@/components/models/ModelOrderToggle'
import { PageHeader } from '@/components/shell/PageHeader'

export function ModelsPage() {
  const bridge = useBridge()
  const [order, setOrder] = useState<ModelOrder>('Speed')
  const [models, setModels] = useState<ModelInfo[]>([])

  useEffect(() => {
    void bridge.getModels(order).then(setModels)
  }, [bridge, order])

  async function refresh() {
    setModels(await bridge.getModels(order))
  }

  return (
    <div>
      <PageHeader title="Models" description="Mock model management for faster-whisper compatible local models. Downloads are not real in Phase 1." />
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <ModelOrderToggle value={order} onChange={setOrder} />
        <AddCustomModelDialog
          onAdd={async (name, source) => {
            await bridge.addCustomModel(name, source)
            await refresh()
          }}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {models.map((model) => (
          <ModelCard
            key={model.tier}
            model={model}
            onDownload={(tier) => {
              void bridge.downloadModel(tier)
              toast.info('Mock download only in Phase 1')
            }}
            onCopyPath={(tier) => {
              void bridge.copyModelPath(tier)
            }}
            onOpenFolder={(tier) => {
              void bridge.openModelFolder(tier)
              toast.info('Mock folder action')
            }}
          />
        ))}
      </div>
    </div>
  )
}
