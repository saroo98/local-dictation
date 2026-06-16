import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { useBridge } from '@/bridge/bridgeContext'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function HelpAboutPage() {
  const bridge = useBridge()
  const [checked, setChecked] = useState(false)

  async function checkUpdates() {
    await bridge.checkForUpdates()
    setChecked(true)
    toast.info('Mock update check only')
  }

  return (
    <div>
      <PageHeader title="Help/About" description="Project context, privacy posture, and Phase 1 migration notes." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" /> Local-first by design
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <p>No cloud transcription, telemetry, analytics, CDN fonts, or automatic network calls are included in Phase 1.</p>
            <p>The UI talks to a typed mock bridge only. Real Python integration is intentionally deferred.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Version</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">0.1.0-phase-1</p>
            <Button type="button" variant="outline" onClick={() => void checkUpdates()}>
              Check for updates
            </Button>
            {checked ? <p className="text-sm text-primary">Mock update check complete.</p> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
