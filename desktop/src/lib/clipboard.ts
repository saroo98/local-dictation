import { toast } from 'sonner'

export async function copyText(text: string) {
  await navigator.clipboard.writeText(text)
}

export async function copyTranscript(text: string): Promise<void> {
  try {
    await copyText(text)
    toast.success('Copied transcript')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Could not copy transcript')
  }
}
