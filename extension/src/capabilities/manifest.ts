export type CapabilityHealthStatus = 'available' | 'degraded' | 'unavailable'

export interface CapabilityManifestEntry {
  id: string
  version: string
  purpose: string
  health: CapabilityHealthStatus
}

export const EXISTING_BROWSER_CAPABILITIES: CapabilityManifestEntry[] = [
  { id: 'browser.click', version: '1.0.0', purpose: 'Activate a visible page control or link', health: 'available' },
  { id: 'browser.fill', version: '1.0.0', purpose: 'Fill a text-compatible form field', health: 'available' },
  { id: 'browser.select_option', version: '1.0.0', purpose: 'Select an option in a native or adapted control', health: 'available' },
  { id: 'browser.choose_date', version: '1.0.0', purpose: 'Choose a date using existing widget support', health: 'available' },
  { id: 'browser.scroll', version: '1.0.0', purpose: 'Scroll the active page or scroll container', health: 'available' },
  { id: 'browser.navigate', version: '1.0.0', purpose: 'Navigate the active tab to a URL', health: 'available' },
  { id: 'browser.wait', version: '1.0.0', purpose: 'Wait for a bounded duration', health: 'available' },
  { id: 'browser.open_new_tab', version: '1.0.0', purpose: 'Open a new browser tab', health: 'available' },
  { id: 'browser.switch_tab', version: '1.0.0', purpose: 'Switch to an existing browser tab', health: 'available' },
  { id: 'browser.close_tab', version: '1.0.0', purpose: 'Close an eligible browser tab', health: 'available' },
  { id: 'browser.focus_existing_tab', version: '1.0.0', purpose: 'Focus an existing browser tab', health: 'available' },
  { id: 'browser.upload', version: '1.0.0', purpose: 'Upload an explicitly requested local file', health: 'available' },
  { id: 'browser.download', version: '1.0.0', purpose: 'Detect and record browser downloads', health: 'available' },
]

export function compactCapabilityManifest(): CapabilityManifestEntry[] {
  return [...EXISTING_BROWSER_CAPABILITIES]
}
