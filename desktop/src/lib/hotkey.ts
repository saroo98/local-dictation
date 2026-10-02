const modifiers = new Set(['<ctrl>', '<alt>', '<shift>', '<cmd>'])
const specialKeys = new Set([
  '<space>', '<enter>', '<esc>', '<up>', '<down>', '<left>', '<right>',
  '<home>', '<end>', '<page_up>', '<page_down>', '<insert>', '<delete>', '<backspace>', '<tab>',
])

export function validHotkey(value: string): boolean {
  if (!value.trim()) return true
  const parts = value.trim().toLowerCase().split('+')
  const key = parts.pop() ?? ''
  return new Set(parts).size === parts.length && parts.every((part) => modifiers.has(part)) &&
    (specialKeys.has(key) || /^<f([1-9]|1[0-9]|2[0-4])>$/.test(key) || /^[a-z0-9]$/.test(key))
}
