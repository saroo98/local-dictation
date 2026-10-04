import { act, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BackendStatusProvider } from '@/bridge/BackendStatusProvider'
import { useBackendStatus } from '@/bridge/useBackendStatus'
import { BridgeContext } from '@/bridge/bridgeContext'
import { createMockBridge } from '@/bridge/mockBridge'
import type { BackendStatus } from '@/bridge/types'

const ready: BackendStatus = { status: 'ready', owned: true, message: 'New launch ready', log_path: '' }
const off: BackendStatus = { status: 'not_running', owned: false, message: 'Old read', log_path: '' }

function Probe() {
  const { backendStatus, startBackend } = useBackendStatus()
  return <><span>{backendStatus?.message}</span><button onClick={() => { void startBackend().catch(() => undefined) }}>Start</button></>
}

describe('backend status request ordering', () => {
  afterEach(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }) })

  it('initializes backend availability once in an initially hidden surface', async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    const bridge = { ...createMockBridge(), getBackendStatus: vi.fn(async () => ready) }
    render(<BridgeContext.Provider value={bridge}><BackendStatusProvider autoStartInTauri={false}><Probe /></BackendStatusProvider></BridgeContext.Provider>)
    expect(await screen.findByText('New launch ready')).toBeInTheDocument()
    expect(bridge.getBackendStatus).toHaveBeenCalledOnce()
  })

  it('publishes availability after the StrictMode setup and cleanup cycle', async () => {
    const bridge = { ...createMockBridge(), getBackendStatus: vi.fn(async () => ready) }
    render(<StrictMode><BridgeContext.Provider value={bridge}><BackendStatusProvider autoStartInTauri={false}><Probe /></BackendStatusProvider></BridgeContext.Provider></StrictMode>)
    expect(await screen.findByText('New launch ready')).toBeInTheDocument()
  })

  it('ignores a status response from before the latest lifecycle request', async () => {
    let resolveRead!: (status: BackendStatus) => void
    const bridge = { ...createMockBridge(), getBackendStatus: vi.fn(() => new Promise<BackendStatus>((resolve) => { resolveRead = resolve })), startBackend: vi.fn(async () => ready) }
    render(<BridgeContext.Provider value={bridge}><BackendStatusProvider autoStartInTauri={false}><Probe /></BackendStatusProvider></BridgeContext.Provider>)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByText('New launch ready')).toBeInTheDocument()
    await act(async () => { resolveRead(off) })
    expect(screen.getByText('New launch ready')).toBeInTheDocument()
    expect(screen.queryByText('Old read')).not.toBeInTheDocument()
  })

  it('reserves one pending lifecycle request and retains a rejected start cause', async () => {
    let reject!: (cause: Error) => void
    const startBackend = vi.fn(() => new Promise<BackendStatus>((_, fail) => { reject = fail }))
    const bridge = { ...createMockBridge(), getBackendStatus: vi.fn(async () => off), startBackend }
    render(<BridgeContext.Provider value={bridge}><BackendStatusProvider autoStartInTauri={false}><Probe /></BackendStatusProvider></BridgeContext.Provider>)
    await userEvent.setup().dblClick(screen.getByRole('button', { name: 'Start' }))
    expect(startBackend).toHaveBeenCalledOnce()
    await act(async () => { reject(new Error('Backend executable missing')) })
    expect(await screen.findByText('Backend executable missing')).toBeInTheDocument()
  })
})
