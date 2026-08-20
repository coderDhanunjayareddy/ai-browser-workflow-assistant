const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')

test('build defines one backend URL and a shared runtime identity', () => {
  const vite = fs.readFileSync(path.join(root, 'vite.config.ts'), 'utf8')
  assert.match(vite, /__BACKEND_URL__/)
  assert.match(vite, /__APP_VERSION__/)
  assert.match(vite, /__BUILD_COMMIT__/)
  assert.match(vite, /__BUILD_ID__/)
})

test('side panel visibly fails closed on runtime mismatch', () => {
  const app = fs.readFileSync(path.join(root, 'src', 'sidepanel', 'App.tsx'), 'utf8')
  assert.match(app, /data-testid="runtime-handshake"/)
  assert.match(app, /RUNTIME MISMATCH/)
  assert.match(app, /RUNTIME UNAVAILABLE/)
  assert.match(app, /runtime\.build_id === BUILD_ID/)
  assert.match(app, /worker\.build_id === BUILD_ID/)
  assert.match(app, /data-testid="runtime-blocked"/)
  assert.match(app, /panel\/worker\/api/)
  assert.match(app, /normalizedRuntimeUrl === BACKEND_URL/)
})
