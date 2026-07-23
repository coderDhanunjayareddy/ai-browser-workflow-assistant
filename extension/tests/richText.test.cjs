const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rich-text-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'rich_text.ts'),
], { cwd: root, stdio: 'pipe' })

const { parseRichTextPayload } = require(path.join(outDir, 'rich_text.js'))

test('plain text rich text payload defaults to replace with formatting preservation', () => {
  const payload = parseRichTextPayload('Hello editor')
  assert.equal(payload.text, 'Hello editor')
  assert.equal(payload.mode, 'replace')
  assert.equal(payload.preserve_formatting, true)
  assert.deepEqual(payload.shortcuts, [])
})

test('JSON rich text payload preserves html, mode and shortcuts', () => {
  const payload = parseRichTextPayload(JSON.stringify({
    text: 'Hello',
    html: '<strong>Hello</strong>',
    mode: 'append',
    preserve_formatting: true,
    shortcuts: ['ctrl+b', 'ctrl+i'],
  }))
  assert.equal(payload.text, 'Hello')
  assert.equal(payload.html, '<strong>Hello</strong>')
  assert.equal(payload.mode, 'append')
  assert.equal(payload.preserve_formatting, true)
  assert.deepEqual(payload.shortcuts, ['ctrl+b', 'ctrl+i'])
})

test('invalid rich text mode safely falls back to replace', () => {
  const payload = parseRichTextPayload(JSON.stringify({ text: 'Hello', mode: 'overwrite-everything' }))
  assert.equal(payload.mode, 'replace')
})
