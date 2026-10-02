import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BackendStatusProvider } from '@/bridge/BackendStatusProvider'
import { BridgeContext } from '@/bridge/bridgeContext'
import { createPythonBridge } from '@/bridge/pythonBridge'
import type { AppState, BackendStatus } from '@/bridge/types'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import { FloatingBubbleSurface } from '@/components/dictation/FloatingBubbleSurface'

type NativeEvent = { event: string; id: number; payload: boolean }
type Target = { kind: string; label?: string }
const callbacks = new Map<number, (event: NativeEvent) => void>()
const subscriptions = new Map<number, { event: string; target: Target; handler: number }>()
let nextId = 0
let state: AppState
let backendStatus: BackendStatus

// Exercise the real Tauri JS API. Only its native IPC boundary is controlled.
async function invoke(command: string, args: Record<string, unknown> = {}) {
  if (command === 'plugin:event|listen') {
    const id = ++nextId
    subscriptions.set(id, args as { event: string; target: Target; handler: number })
    return id
  }
  if (command === 'plugin:event|unlisten') {
    subscriptions.delete(args.eventId as number)
    return
  }
  if (command === 'current_window_visible') return true
  if (command === 'backend_status') return backendStatus
  if (command === 'bridge_call') {
    const request = JSON.parse(args.request as string) as { cmd: string }
    if (request.cmd === 'get-state') return JSON.stringify({ ok: true, data: state })
    if (request.cmd === 'toggle-recording') {
      state = { ...state, recording: true, status: 'recording' }
      return JSON.stringify({ ok: true, data: { accepted: true } })
    }
  }
  throw new Error(`Unexpected native command: ${command}`)
}

function visibility(label: string, visible: boolean) {
  // Tauri 2 delivers emit_to to matching labels AND catch-all Any listeners.
  subscriptions.forEach(({ event, target, handler }, id) => {
    if (event === 'local-dictation:window-visibility' && (target.kind === 'Any' || target.label === label)) {
      callbacks.get(handler)!({ event, id, payload: visible })
    }
  })
}

function Availability() {
  return <span>{useBackendStatus().backendStatus?.status}</span>
}

describe('visibility isolation through the real Tauri event API', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    callbacks.clear()
    subscriptions.clear()
    nextId = 0
    state = {
      recording: false, transcribing: false, waiting_for_target_click: false,
      status: 'idle', latestTranscript: '', activeModel: 'Balanced', activeLanguage: 'English (US)',
      recording_ready: true,
    }
    backendStatus = { status: 'ready', owned: true, message: 'Ready', log_path: '' }
    vi.stubGlobal('isTauri', true)
    vi.stubGlobal('__TAURI_INTERNALS__', {
      metadata: { currentWindow: { label: 'bubble' }, currentWebview: { label: 'bubble' } },
      invoke,
      transformCallback(callback: (event: NativeEvent) => void) {
        const id = ++nextId
        callbacks.set(id, callback)
        return id
      },
    })
    vi.stubGlobal('__TAURI_EVENT_PLUGIN_INTERNALS__', {
      unregisterListener: (_event: string, id: number) => subscriptions.delete(id),
    })
  })
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

  it('keeps the bubble current across repeated transcription and other-window hides', async () => {
    render(<BridgeContext.Provider value={createPythonBridge()}><FloatingBubbleSurface /></BridgeContext.Provider>)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    const button = screen.getByRole('button', { name: 'Toggle recording' })
    for (let cycle = 0; cycle < 4; cycle += 1) {
      state = { ...state, recording: true, status: 'recording' }
      await act(async () => { await vi.advanceTimersByTimeAsync(750) })
      expect(button).toHaveAttribute('title', 'Stop recording')
      state = { ...state, recording: false, transcribing: true, status: 'transcribing' }
      await act(async () => { await vi.advanceTimersByTimeAsync(750) })
      expect(button).toHaveAttribute('title', 'Transcribing')
      visibility(cycle % 2 ? 'main' : 'quick-popover', false)
      state = { ...state, transcribing: false, status: 'idle' }
      await act(async () => { await vi.advanceTimersByTimeAsync(750) })
      expect(button).toHaveAttribute('aria-busy', 'false')
      expect(button).toHaveAttribute('aria-disabled', 'false')
      await act(async () => { fireEvent.click(button); await vi.advanceTimersByTimeAsync(0) })
      expect(button).toHaveAttribute('title', 'Stop recording')
    }
  })

  it('keeps a hidden bubble paused when a different window is shown', async () => {
    const received: AppState[] = []
    const off = createPythonBridge().onState((next) => received.push(next))
    try {
      await vi.advanceTimersByTimeAsync(0)
      visibility('bubble', false)
      state = { ...state, recording: true, status: 'recording' }
      visibility('main', true)
      await vi.advanceTimersByTimeAsync(2000)
      expect(received.at(-1)?.status).toBe('idle')
      visibility('bubble', true)
      await vi.advanceTimersByTimeAsync(0)
      expect(received.at(-1)?.status).toBe('recording')
    } finally { off() }
  })

  it('continues backend availability checks after another window is hidden', async () => {
    render(<BridgeContext.Provider value={createPythonBridge()}><BackendStatusProvider autoStartInTauri={false}><Availability /></BackendStatusProvider></BridgeContext.Provider>)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(screen.getByText('ready')).toBeInTheDocument()
    visibility('quick-popover', false)
    backendStatus = { ...backendStatus, status: 'not_running' }
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(screen.getByText('not_running')).toBeInTheDocument()
  })
})
