import { useCallback, useEffect, useRef, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { toast } from 'sonner'

import { isTauriRuntime } from '@/bridge'
import { useBridge } from '@/bridge/bridgeContext'
import { useRuntimeState } from '@/bridge/useRuntimeState'
import type { ModelInfo, ModelOrder } from '@/bridge/types'
import { AddCustomModelDialog } from '@/components/models/AddCustomModelDialog'
import { ModelCard } from '@/components/models/ModelCard'
import { ModelOrderToggle } from '@/components/models/ModelOrderToggle'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'

export function ModelsPage() {
  const bridge = useBridge()
  const { state, backendReady } = useRuntimeState()
  const [order, setOrder] = useState<ModelOrder>('Speed')
  const [models, setModels] = useState<ModelInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const readId = useRef(0)
  const pendingDownloads = useRef(new Set<string>())
  const canRead = backendReady && state?.connected !== false

  const refresh = useCallback(() => {
    const id = ++readId.current
    return bridge.getModels(order).then((next) => {
      if (id === readId.current) { setModels(next); setError(null); setLoaded(true) }
    }).catch((cause: unknown) => {
      if (id === readId.current) setError(cause instanceof Error ? cause.message : 'Could not load models')
    })
  }, [bridge, order])

  useEffect(() => {
    if (canRead) void refresh()
    return () => { readId.current += 1 }
  }, [canRead, refresh])

  const downloading = models.some((model) => model.download_status === 'downloading')
  useEffect(() => {
    if (!backendReady) return
    let cancelled = false
    let running = false
    let timer: number | undefined
    let nativeVisible: boolean | undefined
    let visibilityVersion = 0
    let unlisten: (() => void) | undefined
    const visible = () => nativeVisible ?? !document.hidden
    const schedule = () => {
      if (downloading && visible()) timer = window.setTimeout(() => { timer = undefined; void tick() }, 1500)
    }
    async function tick() {
      if (cancelled || running || !visible()) return
      running = true
      await refresh()
      running = false
      if (!cancelled) schedule()
    }
    const refreshWhenVisible = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = undefined
      if (visible()) void tick()
    }
    document.addEventListener('visibilitychange', refreshWhenVisible)
    if (isTauriRuntime()) {
      void listen<boolean>('local-dictation:window-visibility', ({ payload }) => {
        visibilityVersion += 1
        nativeVisible = payload
        refreshWhenVisible()
      }).then(async (off) => {
        if (cancelled) { off(); return }
        unlisten = off
        const version = visibilityVersion
        try {
          const initial = await invoke<boolean>('current_window_visible')
          if (!cancelled && version === visibilityVersion && typeof initial === 'boolean') {
            nativeVisible = initial
            if (timer !== undefined) window.clearTimeout(timer)
            timer = undefined
            schedule()
          }
        } catch { /* Keep DOM visibility if native visibility is unavailable. */ }
      }).catch(() => undefined)
    }
    schedule()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
      unlisten?.()
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [backendReady, downloading, refresh])

  async function download(tier: string) {
    if (pendingDownloads.current.has(tier) || !canRead) return
    pendingDownloads.current.add(tier)
    setModels((current) => current.map((model) => model.tier === tier ? { ...model, download_status: 'downloading', download_error: '' } : model))
    try {
      await bridge.downloadModel(tier)
      toast.success(`Download started: ${tier}`)
      await refresh()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Could not start model download'
      setModels((current) => current.map((model) => model.tier === tier ? { ...model, download_status: 'error', download_error: message } : model))
      toast.error(message)
    } finally { pendingDownloads.current.delete(tier) }
  }

  return (
    <div>
      <PageHeader title="Models" description="Manage faster-whisper compatible local models through the active bridge." />
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <ModelOrderToggle value={order} onChange={setOrder} />
        <AddCustomModelDialog
          disabled={!canRead || Boolean(state?.loading)}
          onAdd={async (name, source) => {
            await bridge.addCustomModel(name, source)
            await refresh()
          }}
        />
      </div>
      {error || !canRead ? (
        <div role="alert" className="mb-4 flex items-center gap-3 text-sm">
          <p className="text-destructive">{error ?? state?.connection_error ?? 'Waiting for the backend...'}</p>
          <Button variant="outline" onClick={() => void refresh()} disabled={!backendReady}>Retry models</Button>
        </div>
      ) : null}
      {!loaded && !error && canRead ? <p className="mb-4 text-sm text-muted-foreground">Loading models...</p> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {models.map((model) => (
          <ModelCard
            key={model.tier}
            model={model}
            disabled={!canRead || Boolean(state?.loading)}
            onDownload={(tier) => { void download(tier) }}
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
