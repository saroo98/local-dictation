import { invoke, isTauri } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'

export type TauriWindowPosition = [number, number]

export function isTauriWindowRuntime() {
  return isTauri()
}

export async function showBubbleWindow(position?: [number, number] | null) {
  if (!isTauriWindowRuntime()) return
  await invoke('bubble_show', {
    x: position?.[0] ?? null,
    y: position?.[1] ?? null,
  })
}

export async function hideBubbleWindow() {
  if (!isTauriWindowRuntime()) return
  await invoke('bubble_hide')
}

export async function showQuickPopoverWindow() {
  if (!isTauriWindowRuntime()) return
  await invoke('quick_popover_show')
}

export async function hideQuickPopoverWindow() {
  if (!isTauriWindowRuntime()) return
  await invoke('quick_popover_hide')
}

export async function showMainWindow(route?: string) {
  if (!isTauriWindowRuntime()) return
  await invoke('main_window_show', { route: route ?? null })
}

export async function hideAppToTray() {
  if (!isTauriWindowRuntime()) return
  await invoke('app_hide_to_tray')
}

export async function quitTauriApp() {
  if (!isTauriWindowRuntime()) return
  await invoke('app_quit')
}

export async function startBubbleDrag() {
  if (!isTauriWindowRuntime()) return
  await getCurrentWindow().startDragging()
}

export async function watchCurrentWindowMoved(onMoved: (position: TauriWindowPosition) => void) {
  if (!isTauriWindowRuntime()) return () => {}
  return getCurrentWindow().onMoved(({ payload }) => {
    onMoved([payload.x, payload.y])
  })
}

export async function watchCurrentWindowVisibility(onVisible: (visible: boolean) => void) {
  if (!isTauriWindowRuntime()) return () => {}
  // Global listeners also receive hide/show events targeted at other windows.
  return getCurrentWindow().listen<boolean>('local-dictation:window-visibility', ({ payload }) => {
    onVisible(payload)
  })
}
