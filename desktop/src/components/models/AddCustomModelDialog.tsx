import { Plus } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function AddCustomModelDialog({ onAdd, disabled = false }: { onAdd: (name: string, source: string) => Promise<void>; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [source, setSource] = useState('')
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)

  async function submit() {
    if (submitting.current || disabled) return
    submitting.current = true
    setPending(true)
    try {
      await onAdd(name, source)
      setName('')
      setSource('')
      setOpen(false)
      toast.success('Custom model added')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not add model')
    } finally { submitting.current = false; setPending(false) }
  }

  return (
    <div>
      <Button type="button" variant="outline" disabled={disabled || pending} onClick={() => setOpen((next) => !next)} aria-label="Add custom model">
        <Plus className="h-4 w-4" /> Add custom model
      </Button>
      {open && (
        <div className="mt-3 rounded-xl border border-border bg-card p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="custom-model-name">Display name</Label>
              <Input id="custom-model-name" value={name} disabled={disabled || pending} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="custom-model-source">Repo ID or local folder</Label>
              <Input id="custom-model-source" value={source} disabled={disabled || pending} onChange={(event) => setSource(event.target.value)} />
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <Button type="button" size="sm" disabled={disabled || pending} onClick={() => void submit()}>
              {pending ? 'Saving...' : 'Save custom model'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
