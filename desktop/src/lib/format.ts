export function truncateText(text: string, max = 120) {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1).trim()}...`
}

export function formatBytes(bytes: number) {
  if (!bytes) return 'Custom'
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`
  return `${Math.round(bytes / 1_000_000)} MB`
}
