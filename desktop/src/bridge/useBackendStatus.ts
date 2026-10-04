import { useContext } from 'react'

import { BackendStatusContext } from '@/bridge/BackendStatusContext'

export function useBackendStatus() {
  const value = useContext(BackendStatusContext)
  if (!value) {
    throw new Error('useBackendStatus must be used inside BackendStatusProvider.')
  }
  return value
}
