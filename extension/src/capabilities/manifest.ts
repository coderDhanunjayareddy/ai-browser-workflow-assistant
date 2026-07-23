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
import v4BrowserCapabilityManifest from '../../../shared/v4_browser_capabilities.json'

export interface BrowserCapabilityManifestEntry {
  capability_id: string
  version: string
  category: string
  description: string
  dependencies: string[]
  feature_flag: string
  maturity_level: number
  target_maturity_level: number
  supported_browsers: string[]
  supported_websites: string[]
  site_adapters: string[]
  benchmarks: string[]
  metrics: string[]
  known_limitations: string[]
  rollout_status: string
  safety_constraints: string[]
  failure_classes: string[]
  owner: string
}

export const EXISTING_BROWSER_CAPABILITIES: CapabilityManifestEntry[] = capabilityManifest.map((capability) => ({
  ...capability,
  health: 'available',
}))

export function compactCapabilityManifest(): CapabilityManifestEntry[] {
  return [...EXISTING_BROWSER_CAPABILITIES]
}

export const V4_WAVE1_BROWSER_CAPABILITIES: BrowserCapabilityManifestEntry[] =
  v4BrowserCapabilityManifest as BrowserCapabilityManifestEntry[]

export function compactV4BrowserCapabilityManifest(): Array<{
  capability_id: string
  version: string
  feature_flag: string
  maturity_level: number
  rollout_status: string
}> {
  return V4_WAVE1_BROWSER_CAPABILITIES.map((capability) => ({
    capability_id: capability.capability_id,
    version: capability.version,
    feature_flag: capability.feature_flag,
    maturity_level: capability.maturity_level,
    rollout_status: capability.rollout_status,
  }))
}
