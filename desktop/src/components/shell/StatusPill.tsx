import { useEffect, useState } from 'react'

import { useBridge } from '@/bridge/bridgeContext'
import type { AppState } from '@/bridge/types'
import { Badge } from '@/components/ui/badge'

const labels: Record<AppState['status'], string> = {
  idle: 'Idle',
  recording: 'Recording',
  transcribing: 'Transcribing',
  'paste-ready': 'Paste ready',
  error: 'Error',
}

export function StatusPill() {
  const bridge = useBridge()
  const [state, setState] = useState<AppState | null>(null)

  useEffect(() => {
    let mounted = true
    void bridge
      .getState()
      .then((next) => {
        if (mounted) setState(next)
      })
      .catch(() => {
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

  return <Badge className="bg-secondary/70">{state ? labels[state.status] : 'Loading'}</Badge>
}
