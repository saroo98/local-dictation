import type { ReactNode } from 'react'

import { Label } from '@/components/ui/label'

export function SettingsField({
  id,
  label,
  help,
  children,
}: {
  id: string
  label: string
  help?: string
  children: ReactNode
}) {
  return (
    <div className="grid gap-2 md:grid-cols-[180px_1fr] md:items-center">
      <div>
        <Label htmlFor={id}>{label}</Label>
        {help ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{help}</p> : null}
      </div>
      {children}
    </div>
  )
}
