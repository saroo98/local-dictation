import { Input } from '@/components/ui/input'

export function HotkeyInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Input
      id="hotkey"
      value={value}
      onFocus={(event) => event.currentTarget.select()}
      onKeyDown={(event) => {
        if (event.key.length === 1) {
          event.preventDefault()
          onChange(event.key.toUpperCase())
        }
      }}
      onChange={(event) => onChange(event.target.value)}
      className="max-w-xs"
    />
  )
}
