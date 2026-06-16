import { createMockBridge } from '@/bridge/mockBridge'
import type { Bridge } from '@/bridge/types'

let bridge: Bridge | undefined

export function getBridge(): Bridge {
  if (!bridge) {
    bridge = createMockBridge()
  }
  return bridge
}
