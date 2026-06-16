import { Mic, Square } from 'lucide-react'

import type { AppState } from '@/bridge/types'
import { Button } from '@/components/ui/button'

export function RecordButton({ state, onToggle, disabled = false }: { state: AppState | null; onToggle: () => void; disabled?: boolean }) {
  const recording = Boolean(state?.recording)

  return (
    <Button
      type="button"
      size="lg"
      className="h-28 w-28 flex-col rounded-full text-base shadow-xl"
      variant={recording ? 'destructive' : 'default'}
      onClick={onToggle}
      disabled={disabled}
      aria-label={recording ? 'Stop recording' : 'Start recording'}
    >
      {recording ? <Square className="h-8 w-8 fill-current" strokeWidth={1.8} /> : <Mic className="h-8 w-8" strokeWidth={1.8} />}
      {recording ? 'Stop' : 'Start'}
    </Button>
  )
}
