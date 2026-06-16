import { Download } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { formatTime } from '@/lib/time'

export function ExportRow({ name, createdAt, format }: { name: string; createdAt: string; format: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border/70 bg-card p-4">
      <div>
        <p className="font-medium">{name}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {format} | {formatTime(createdAt)}
        </p>
      </div>
      <Button type="button" variant="outline" size="sm">
        <Download className="h-3.5 w-3.5" /> Export
      </Button>
    </div>
  )
}
