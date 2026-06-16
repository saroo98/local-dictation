import type { ComponentType } from 'react'
import { Download, HelpCircle, History, Mic, Settings, SquareStack } from 'lucide-react'

import { ExportsPage } from '@/pages/ExportsPage'
import { HelpAboutPage } from '@/pages/HelpAboutPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { ModelsPage } from '@/pages/ModelsPage'
import { RecordingPage } from '@/pages/RecordingPage'
import { SettingsPage } from '@/pages/SettingsPage'

export type RouteId = 'recording' | 'history' | 'models' | 'settings' | 'exports' | 'help'

export interface AppRoute {
  id: RouteId
  label: string
  title: string
  icon: ComponentType<{ className?: string; strokeWidth?: number }>
  component: ComponentType
}

export const routes: AppRoute[] = [
  { id: 'recording', label: 'Recording', title: 'Recording', icon: Mic, component: RecordingPage },
  { id: 'history', label: 'History', title: 'History', icon: History, component: HistoryPage },
  { id: 'models', label: 'Models', title: 'Models', icon: SquareStack, component: ModelsPage },
  { id: 'settings', label: 'Settings', title: 'Settings', icon: Settings, component: SettingsPage },
  { id: 'exports', label: 'Exports', title: 'Exports', icon: Download, component: ExportsPage },
  { id: 'help', label: 'Help/About', title: 'Help/About', icon: HelpCircle, component: HelpAboutPage },
]
