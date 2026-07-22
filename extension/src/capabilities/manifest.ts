export type CapabilityHealthStatus = 'available' | 'degraded' | 'unavailable'

export interface CapabilityManifestEntry {
  id: string
  version: string
  purpose: string
  health: CapabilityHealthStatus
  permissions?: string[]
  constraints?: string[]
  environments?: string[]
}

import capabilityManifest from '../../../shared/v3_capabilities.json'

export const EXISTING_BROWSER_CAPABILITIES: CapabilityManifestEntry[] = capabilityManifest.map((capability) => ({
  ...capability,
  health: 'available',
}))

export function compactCapabilityManifest(): CapabilityManifestEntry[] {
  return [...EXISTING_BROWSER_CAPABILITIES]
}
