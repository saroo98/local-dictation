import type { ModelOrder } from '@/bridge/types'
import { Button } from '@/components/ui/button'

export function ModelOrderToggle({ value, onChange }: { value: ModelOrder; onChange: (value: ModelOrder) => void }) {
  return (
    <div className="inline-flex rounded-xl border border-border bg-card p-1">
      <Button
        type="button"
        size="sm"
        variant={value === 'Speed' ? 'default' : 'ghost'}
        onClick={() => onChange('Speed')}
        aria-label="Speed order"
        aria-pressed={value === 'Speed'}
      >
        Speed
      </Button>
      <Button
        type="button"
        size="sm"
        variant={value === 'Accuracy' ? 'default' : 'ghost'}
        onClick={() => onChange('Accuracy')}
        aria-label="Accuracy order"
        aria-pressed={value === 'Accuracy'}
      >
        Accuracy
      </Button>
    </div>
  )
}
