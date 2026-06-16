export function formatTime(value: string | null) {
  if (!value) return 'Earlier'

  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}
