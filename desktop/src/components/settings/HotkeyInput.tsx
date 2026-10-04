import { Input } from '@/components/ui/input'
import type { KeyboardEvent } from 'react'

export function HotkeyInput({ value, onChange, disabled = false }: { value: string; onChange: (value: string) => void; disabled?: boolean }) {
  return (
    <Input
      id="hotkey"
      value={value}
      disabled={disabled}
      onFocus={(event) => event.currentTarget.select()}
      onKeyDown={(event) => {
        const nextHotkey = hotkeyFromKeyboardEvent(event)
        if (nextHotkey !== null) {
          event.preventDefault()
          if (nextHotkey !== 'keep-current') onChange(nextHotkey)
        }
      }}
      onChange={(event) => onChange(event.target.value)}
      className="max-w-xs"
    />
  )
}

function hotkeyFromKeyboardEvent(event: KeyboardEvent<HTMLInputElement>): string | 'keep-current' | null {
  if (event.key === 'Tab') return null
  if (event.key === 'Escape') return 'keep-current'
  if (event.key === 'Backspace' || event.key === 'Delete') return ''
  if (['Control', 'Alt', 'Shift', 'Meta'].includes(event.key)) return 'keep-current'

  const key = normalizeKey(event.key)
  if (!key) return null

  const parts: string[] = []
  if (event.ctrlKey) parts.push('<ctrl>')
  if (event.altKey) parts.push('<alt>')
  if (event.shiftKey) parts.push('<shift>')
  if (event.metaKey) parts.push('<cmd>')
  parts.push(key)
  return parts.join('+')
}

function normalizeKey(key: string): string {
  const aliases: Record<string, string> = {
    ' ': '<space>', Spacebar: '<space>', Space: '<space>', Enter: '<enter>',
    ArrowUp: '<up>', ArrowDown: '<down>', ArrowLeft: '<left>', ArrowRight: '<right>',
    Home: '<home>', End: '<end>', PageUp: '<page_up>', PageDown: '<page_down>', Insert: '<insert>',
  }
  if (aliases[key]) return aliases[key]
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(key)) return `<${key.toLowerCase()}>`
  return /^[a-z0-9]$/i.test(key) ? key.toLowerCase() : ''
}
