import { AlertTriangle, Check, Clipboard, Ellipsis, Play, Square } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
import { useRuntimeState } from '@/bridge/useRuntimeState'
import { toast } from 'sonner'
import type { AppState } from '@/bridge/types'
import { cn } from '@/lib/cn'
import {
  showMainWindow,
  showQuickPopoverWindow,
  startBubbleDrag,
  watchCurrentWindowMoved,
  type TauriWindowPosition,
} from '@/tauri/windowControls'

const iconClasses: Record<AppState['status'], string> = {
  idle: 'bg-primary text-primary-foreground',
  recording: 'bg-destructive text-destructive-foreground',
  transcribing: 'bg-amber-500 text-amber-950',
  'paste-ready': 'bg-sky-600 text-white',
  error: 'bg-destructive text-destructive-foreground',
}

function StateIcon({ status }: { status: AppState['status'] }) {
  if (status === 'recording') return <Square className="h-5 w-5 fill-current" strokeWidth={1.8} />
  if (status === 'transcribing') return <Ellipsis className="h-5 w-5" strokeWidth={2} />
  if (status === 'paste-ready') return <Clipboard className="h-[18px] w-[18px]" strokeWidth={1.9} />
  if (status === 'error') return <AlertTriangle className="h-[18px] w-[18px]" strokeWidth={1.9} />
  if (status === 'idle') return <Play className="ml-0.5 h-5 w-5 fill-current" strokeWidth={1.8} />
  return <Check className="h-5 w-5" strokeWidth={1.8} />
}

export function FloatingBubbleSurface() {
  const bridge = useBridge()
  const { state } = useRuntimeState()
  const [pending, setPending] = useState(false)
  const actionPending = useRef(false)
  const pointerStart = useRef<{ x: number; y: number } | null>(null)
  const dragStarted = useRef(false)
  const suppressNextClick = useRef(false)
  const runtimeState = useRef(state)
  const status = state?.connected === false ? 'error' : state?.loading ? 'transcribing' : state?.status ?? 'idle'
  const recordingDisabled = pending || !state || Boolean(state.loading || state.transcribing) || state.recording_ready === false || state.connected === false

  useEffect(() => { runtimeState.current = state }, [state])

  useEffect(() => {
    let cancelled = false
    let unlisten: (() => void) | undefined
    let latestPosition: TauriWindowPosition | null = null
    let writing = false
    let saveTimer: number | undefined

    function schedule(delay: number) {
      if (saveTimer !== undefined) window.clearTimeout(saveTimer)
      saveTimer = window.setTimeout(() => { saveTimer = undefined; void savePosition() }, delay)
    }

    async function savePosition() {
      if (cancelled || writing || !latestPosition) return
      const current = runtimeState.current
      if (current?.connected === false || current?.loading || current?.settings_error) {
        schedule(1000)
        return
      }
      const position = latestPosition
      writing = true
      let failed = false
      try {
        await bridge.saveSettings({ bubble_position: position })
        if (latestPosition === position) latestPosition = null
      } catch {
        // Retain the latest move until a busy or disconnected backend recovers.
        failed = true
      } finally {
        writing = false
        if (!cancelled && latestPosition) schedule(failed ? 1000 : 350)
      }
    }

    void watchCurrentWindowMoved((position: TauriWindowPosition) => {
      if (cancelled) return
      latestPosition = position
      schedule(350)
    }).then((nextUnlisten) => {
      if (cancelled) {
        nextUnlisten()
      } else {
        unlisten = nextUnlisten
      }
    }).catch(() => undefined)

    return () => {
      cancelled = true
      if (saveTimer !== undefined) window.clearTimeout(saveTimer)
      unlisten?.()
    }
  }, [bridge])

  async function toggleRecording() {
    if (actionPending.current) return
    if (recordingDisabled) {
      if (state?.connected === false || state?.recording_ready === false) {
        await showMainWindow('help').catch(() => undefined)
      }
      return
    }
    actionPending.current = true
    setPending(true)
    try {
      await bridge.toggleRecording()
      await bridge.getState()
    } catch {
      await showMainWindow('help').catch(() => toast.error('Could not open recovery controls'))
    } finally { actionPending.current = false; setPending(false) }
  }

  async function showPopover(event: MouseEvent) {
    event.preventDefault()
    try {
      await showQuickPopoverWindow()
    } catch {
      await showMainWindow('history').catch(() => toast.error('Could not open history'))
    }
  }

  async function beginDrag(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return
    pointerStart.current = { x: event.clientX, y: event.clientY }
    dragStarted.current = false
  }

  async function maybeDrag(event: PointerEvent<HTMLButtonElement>) {
    if (!pointerStart.current || dragStarted.current || event.buttons !== 1) return
    const deltaX = event.clientX - pointerStart.current.x
    const deltaY = event.clientY - pointerStart.current.y
    if (Math.hypot(deltaX, deltaY) < 5) return

    dragStarted.current = true
    suppressNextClick.current = true
    try {
      await startBubbleDrag()
    } catch {
      suppressNextClick.current = false
    }
  }

  function endDrag() {
    pointerStart.current = null
    if (dragStarted.current) {
      window.setTimeout(() => {
        suppressNextClick.current = false
      }, 150)
    }
  }

  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    if (suppressNextClick.current) {
      event.preventDefault()
      suppressNextClick.current = false
      return
    }
    void toggleRecording()
  }

  return (
    <main className="grid h-screen w-screen place-items-center bg-transparent p-1">
      <button
        type="button"
        aria-label="Toggle recording"
        aria-disabled={recordingDisabled}
        aria-busy={pending || Boolean(state?.loading || state?.transcribing)}
        title={state?.connection_error || state?.error || (state?.loading ? 'Loading recording resources' : state?.transcribing ? 'Transcribing' : state?.recording ? 'Stop recording' : 'Start recording. Right-click for history.')}
        onPointerDown={(event) => void beginDrag(event)}
        onPointerMove={(event) => void maybeDrag(event)}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onClick={handleClick}
        onContextMenu={(event) => void showPopover(event)}
        className={cn(
          'grid h-11 w-11 place-items-center rounded-full border border-white/20 shadow-2xl shadow-slate-950/25 outline-none transition hover:scale-[1.03] focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          iconClasses[status],
        )}
      >
        <StateIcon status={status} />
      </button>
    </main>
  )
}
