import { AlertTriangle, Check, Clipboard, Ellipsis, Play, Square } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
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
  transcribing: 'bg-amber-500 text-white',
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
  const [state, setState] = useState<AppState | null>(null)
  const pointerStart = useRef<{ x: number; y: number } | null>(null)
  const dragStarted = useRef(false)
  const suppressNextClick = useRef(false)
  const saveTimer = useRef<number | undefined>(undefined)
  const status = state?.status ?? 'idle'

  useEffect(() => {
    let mounted = true
    void bridge.getState().then((next) => {
      if (mounted) setState(next)
    }).catch(() => {
      if (mounted) {
        setState({
          recording: false,
          transcribing: false,
          waiting_for_target_click: false,
          status: 'error',
          latestTranscript: '',
          activeModel: '',
          activeLanguage: '',
        })
      }
    })
    const off = bridge.onState(setState)
    return () => {
      mounted = false
      off()
    }
  }, [bridge])

  useEffect(() => {
    let cancelled = false
    let unlisten: (() => void) | undefined

    void watchCurrentWindowMoved((position: TauriWindowPosition) => {
      if (cancelled) return
      if (saveTimer.current !== undefined) window.clearTimeout(saveTimer.current)
      saveTimer.current = window.setTimeout(() => {
        void bridge.getSettings().then((settings) => {
          return bridge.saveSettings({
            ...settings,
            bubble_position: position,
          })
        }).catch(() => {
          // Position persistence should never interrupt the floating control.
        })
      }, 350)
    }).then((nextUnlisten) => {
      if (cancelled) {
        nextUnlisten()
      } else {
        unlisten = nextUnlisten
      }
    })

    return () => {
      cancelled = true
      if (saveTimer.current !== undefined) window.clearTimeout(saveTimer.current)
      unlisten?.()
    }
  }, [bridge])

  async function toggleRecording() {
    try {
      await bridge.toggleRecording()
      setState(await bridge.getState())
    } catch {
      await showMainWindow('help')
    }
  }

  async function showPopover(event: MouseEvent) {
    event.preventDefault()
    try {
      await showQuickPopoverWindow()
    } catch {
      await showMainWindow('history')
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
