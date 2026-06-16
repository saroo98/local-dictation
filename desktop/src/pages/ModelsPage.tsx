import { useCallback, useEffect, useState } from 'react'
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

  const loadModels = useCallback(() => {
    return bridge.getModels(order)
  }, [bridge, order])

  const refresh = useCallback(async () => {
    setModels(await loadModels())
  }, [loadModels])

  useEffect(() => {
    let cancelled = false
    void loadModels()
      .then((next) => {
        if (!cancelled) setModels(next)
      })
      .catch(() => {
        if (!cancelled) setModels([])
      })
    return () => {
      cancelled = true
    }
  }, [loadModels])

  useEffect(() => {
    if (!models.some((model) => model.download_status === 'downloading')) return undefined
    const interval = window.setInterval(() => {
      void loadModels().then(setModels).catch(() => setModels([]))
    }, 1500)
    return () => window.clearInterval(interval)
  }, [models, loadModels])

  return (
    <div>
      <PageHeader title="Models" description="Manage faster-whisper compatible local models through the active bridge." />
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
              void bridge
                .downloadModel(tier)
                .then(async () => {
                  toast.success(`Download started: ${tier}`)
                  await refresh()
                })
                .catch((error: unknown) => {
                  toast.error(error instanceof Error ? error.message : 'Could not start model download')
                })
            }}
            onCopyPath={(tier) => {
              void bridge
                .copyModelPath(tier)
                .then(() => toast.success('Model path copied'))
                .catch((error: unknown) => {
                  toast.error(error instanceof Error ? error.message : 'Could not copy model path')
                })
            }}
            onOpenFolder={(tier) => {
              void bridge.openModelFolder(tier).catch((error: unknown) => {
                toast.error(error instanceof Error ? error.message : 'Could not open model folder')
              })
            }}
          />
        ))}
      </div>
    </div>
  )
}
