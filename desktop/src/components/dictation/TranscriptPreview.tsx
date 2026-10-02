import { Copy, History } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { copyTranscript } from '@/lib/clipboard'

export function TranscriptPreview({ text, onOpenHistory }: { text: string; onOpenHistory: () => void }) {
  async function copyLatest() {
    await copyTranscript(text)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Latest transcript</CardTitle>
        <CardDescription>Your latest completed transcript.</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="min-h-20 rounded-xl border border-border/70 bg-background p-4 text-sm leading-6 text-foreground">
          {text || 'Start and stop recording to create a transcript.'}
        </p>
        <div className="mt-4 flex gap-2">
          <Button type="button" variant="outline" onClick={copyLatest} disabled={!text}>
            <Copy className="h-4 w-4" /> Copy last
          </Button>
          <Button type="button" variant="secondary" onClick={onOpenHistory}>
            <History className="h-4 w-4" /> Open History
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
