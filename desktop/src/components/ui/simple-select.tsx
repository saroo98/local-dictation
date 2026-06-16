import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/cn"

export interface SimpleSelectOption {
  label: string
  value: string
}

export function SimpleSelect({
  id,
  ariaLabel,
  value,
  options,
  onValueChange,
  className,
}: {
  id?: string
  ariaLabel?: string
  value: string
  options: SimpleSelectOption[]
  onValueChange: (value: string) => void
  className?: string
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger id={id} aria-label={ariaLabel} className={cn(className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
