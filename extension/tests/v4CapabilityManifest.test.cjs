const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'v4-capability-manifest-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--resolveJsonModule',
  '--esModuleInterop',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'capabilities', 'manifest.ts'),
], { cwd: root, stdio: 'pipe' })

function findCompiledManifest(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      const found = findCompiledManifest(full)
      if (found) return found
    } else if (entry.name === 'manifest.js' && full.includes(`${path.sep}capabilities${path.sep}`)) {
      return full
    }
  }
  return null
}

const compiledManifest = findCompiledManifest(outDir)
assert.ok(compiledManifest, 'compiled capability manifest was emitted')

const {
  V4_WAVE1_BROWSER_CAPABILITIES,
  compactV4BrowserCapabilityManifest,
} = require(compiledManifest)

test('V4 Wave 1 capability manifest is available to the extension', () => {
  assert.ok(V4_WAVE1_BROWSER_CAPABILITIES.length >= 16)
  const smartWaits = V4_WAVE1_BROWSER_CAPABILITIES.find((capability) =>
    capability.capability_id === 'browser.waits.smart')
  assert.ok(smartWaits)
  assert.equal(smartWaits.feature_flag, 'V4_SMART_WAITS')
  assert.equal(smartWaits.target_maturity_level, 5)
})

test('compact V4 browser manifest preserves rollout and maturity metadata', () => {
  const compact = compactV4BrowserCapabilityManifest()
  assert.equal(compact.length, V4_WAVE1_BROWSER_CAPABILITIES.length)
  assert.deepEqual(Object.keys(compact[0]).sort(), [
    'capability_id',
    'feature_flag',
    'maturity_level',
    'rollout_status',
    'version',
  ])
})
