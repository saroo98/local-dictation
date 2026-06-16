import { Copy, Download, FolderOpen } from 'lucide-react'
import { toast } from 'sonner'

import type { ModelInfo } from '@/bridge/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface ModelCardProps {
  model: ModelInfo
  onDownload: (tier: string) => void
  onCopyPath: (tier: string) => void
  onOpenFolder: (tier: string) => void
}

export function ModelCard({ model, onDownload, onCopyPath, onOpenFolder }: ModelCardProps) {
  return (
    <Card data-testid="model-card" className="flex flex-col">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{model.tier}</CardTitle>
            <CardDescription>
              {model.model_name} | {model.size_text}
            </CardDescription>
          </div>
          <Badge className={model.available ? 'border-primary/40 text-primary' : undefined}>
            {model.available ? 'Installed' : 'Not installed'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <p className="text-sm leading-6 text-muted-foreground">{model.description}</p>
        <div className="rounded-xl bg-secondary/60 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">{model.repo_id}</p>
          <p className="mt-1 truncate">{model.cache_dir}</p>
        </div>
        <div className="mt-auto flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={model.available} onClick={() => onDownload(model.tier)}>
            <Download className="h-3.5 w-3.5" /> {model.available ? 'Installed' : 'Download'}
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={() => onOpenFolder(model.tier)}>
            <FolderOpen className="h-3.5 w-3.5" /> Open folder
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              onCopyPath(model.tier)
              toast.success('Model path copied')
            }}
          >
            <Copy className="h-3.5 w-3.5" /> Copy path
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
