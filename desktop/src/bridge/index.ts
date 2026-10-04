import { isTauri } from '@tauri-apps/api/core'

import { createMockBridge } from '@/bridge/mockBridge'
import { createPythonBridge } from '@/bridge/pythonBridge'
import type { Bridge } from '@/bridge/types'

let bridge: Bridge | undefined

export function isTauriRuntime(): boolean {
  return isTauri()
}

export function createBridgeForRuntime(useLocalBridge = isTauriRuntime()): Bridge {
  return useLocalBridge ? createPythonBridge() : createMockBridge()
}

export function getBridgeRuntimeLabel(useLocalBridge = isTauriRuntime()): string {
  return useLocalBridge ? 'Local bridge' : 'Mock UI'
}

export function getBridge(): Bridge {
  if (!bridge) {
    bridge = createBridgeForRuntime()
  }
  return bridge
}
