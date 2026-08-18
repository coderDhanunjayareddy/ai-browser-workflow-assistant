const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'exact-target-verification-'))
execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020', '--lib', 'ES2020,DOM', '--module', 'commonjs', '--moduleResolution', 'node',
  '--strict', '--skipLibCheck', '--outDir', outDir,
  path.join(root, 'src', 'content', 'exact_target_verification.ts'),
], { cwd: root, stdio: 'pipe' })

const { verifyExactOpenedTarget } = require(path.join(outDir, 'exact_target_verification.js'))

class MockInput {}
global.HTMLInputElement = MockInput

function element({ text = '', title = '', aria = '', value = '' } = {}) {
  const node = value ? new MockInput() : {}
  node.value = value
  node.textContent = text
  node.getAttribute = (name) => name === 'title' ? title : name === 'aria-label' ? aria : ''
  node.getBoundingClientRect = () => ({ width: 100, height: 30 })
  return node
}

function installPage(hostname, selectorMap) {
  global.window = {
    location: { hostname },
    getComputedStyle: () => ({ display: 'block', visibility: 'visible' }),
  }
  global.document = {
    querySelectorAll: (selector) => selectorMap[selector] || [],
  }
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('WhatsApp chat verification accepts only the exact visible conversation header', () => {
  installPage('web.whatsapp.com', { 'header [title]': [element({ title: 'Teja Spc' })] })
  const exact = verifyExactOpenedTarget({ expected_name: 'Teja Spc', semantic_kind: 'recipient', observed_origin: 'https://web.whatsapp.com' })
  assert.equal(exact.required, true)
  assert.equal(exact.verified, true)
  assert.equal(exact.target_kind, 'chat')

  const wrong = verifyExactOpenedTarget({ expected_name: 'Teja', semantic_kind: 'recipient', observed_origin: 'https://web.whatsapp.com' })
  assert.equal(wrong.verified, false)
  assert.equal(wrong.observed_name, 'Teja Spc')
})

test('Gmail and Docs postconditions bind exact thread subject and document title', () => {
  installPage('mail.google.com', { '[role="main"] h2': [element({ text: 'Synthetic Day 3 Thread' })] })
  assert.equal(verifyExactOpenedTarget({ expected_name: 'Synthetic Day 3 Thread', semantic_kind: 'thread', observed_origin: 'https://mail.google.com' }).verified, true)

  installPage('docs.google.com', { 'input.docs-title-input': [element({ value: 'Synthetic Day 3 Doc' })] })
  assert.equal(verifyExactOpenedTarget({ expected_name: 'Synthetic Day 3 Doc', semantic_kind: 'document', observed_origin: 'https://docs.google.com' }).verified, true)
})
