export function formatTime(value: string | null) {
  if (!value) return 'Earlier'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Earlier'

  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}
