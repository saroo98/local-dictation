import { Search } from 'lucide-react'

import { Input } from '@/components/ui/input'

export function HistorySearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="relative block">
      <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" strokeWidth={1.8} />
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search transcripts"
        className="pl-9"
      />
    </label>
  )
}
