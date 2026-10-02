import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/cn"
import type { ReactNode } from "react"

export interface SimpleSelectOption {
  label: string
  value: string
  content?: ReactNode
  selectedContent?: ReactNode
  disabled?: boolean
}

export function SimpleSelect({
  id,
  ariaLabel,
  value,
  options,
  onValueChange,
  className,
  disabled,
}: {
  id?: string
  ariaLabel?: string
  value: string
  options: SimpleSelectOption[]
  onValueChange: (value: string) => void
  className?: string
  disabled?: boolean
}) {
  const selectedOption = options.find((option) => option.value === value)

  return (
    <Select value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectTrigger id={id} aria-label={ariaLabel} className={cn(className)}>
        {selectedOption?.selectedContent ?? <SelectValue />}
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value} textValue={option.label} disabled={option.disabled}>
            {option.content ?? option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
