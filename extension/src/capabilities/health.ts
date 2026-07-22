import type { CapabilityHealthStatus, CapabilityManifestEntry } from './manifest'

export interface CapabilityHealth {
  id: string
  status: CapabilityHealthStatus
  reason?: string
}

export function summarizeCapabilityHealth(capabilities: CapabilityManifestEntry[]): CapabilityHealth[] {
  return capabilities.map((capability) => ({
    id: capability.id,
    status: capability.health,
  }))
}
