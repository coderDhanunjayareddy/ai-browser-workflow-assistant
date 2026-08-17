const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const manifest = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, '..', 'manifest.json'), 'utf8'),
)

test('debugger is a required permission because Chrome forbids it as optional', () => {
  assert.ok(manifest.permissions.includes('debugger'))
  assert.ok(!manifest.optional_permissions?.includes('debugger'))
})

test('native messaging remains disabled until a separately reviewed capability requires it', () => {
  assert.ok(!manifest.permissions.includes('nativeMessaging'))
  assert.ok(!manifest.optional_permissions?.includes('nativeMessaging'))
})
