const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'widget-adapters-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'widget_adapters.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  chooseWidgetAdapter,
  isSafeWidgetAction,
} = require(path.join(outDir, 'widget_adapters.js'))

function action(action_type, description, value = null, safety_level = 'safe') {
  return {
    action_id: `${action_type}-1`,
    action_type,
    target_selector: '#target',
    value,
    description,
    safety_level,
  }
}

function descriptor(kind, overrides = {}) {
  return {
    kind,
    visible: true,
    ...overrides,
  }
}

test('date picker adapter is selected for date actions', () => {
  const selected = chooseWidgetAdapter(action('choose_date', 'Choose check-in date', '15'), [
    descriptor('date_picker', { role: 'dialog' }),
  ])
  assert.equal(selected, 'date_picker')
})

test('combobox adapter is selected for existing option selection', () => {
  const selected = chooseWidgetAdapter(action('select_option', 'Choose city', 'Paris'), [
    descriptor('combobox', { role: 'combobox', ariaExpanded: 'false' }),
  ])
  assert.equal(selected, 'combobox')
})

test('combobox adapter supports searchable dropdown intent', () => {
  const selected = chooseWidgetAdapter(action('select_option', 'Search and select country', 'India'), [
    descriptor('combobox', { role: 'combobox', hasListbox: true }),
  ])
  assert.equal(selected, 'combobox')
})

test('autocomplete adapter is selected for suggestion inputs', () => {
  const selected = chooseWidgetAdapter(action('fill', 'Type destination', 'Hyderabad'), [
    descriptor('autocomplete', { role: 'combobox', autocomplete: 'list' }),
  ])
  assert.equal(selected, 'autocomplete')
})

test('cookie banner adapter is selected when banner is present', () => {
  const selected = chooseWidgetAdapter(action('click', 'Accept cookies'), [
    descriptor('cookie_banner', { text: 'We use cookies' }),
  ])
  assert.equal(selected, 'cookie_banner')
})

test('cookie banner absent leaves normal execution unchanged', () => {
  const selected = chooseWidgetAdapter(action('click', 'Accept cookies'), [])
  assert.equal(selected, null)
})

test('modal dialog adapter is selected when modal is present', () => {
  const selected = chooseWidgetAdapter(action('click', 'Close modal'), [
    descriptor('modal_dialog', { role: 'dialog', hasDialog: true }),
  ])
  assert.equal(selected, 'modal_dialog')
})

test('destructive actions are never handled by widget adapters', () => {
  const destructive = action('click', 'Delete account', null, 'safe')
  assert.equal(isSafeWidgetAction(destructive), false)
  assert.equal(chooseWidgetAdapter(destructive, [descriptor('modal_dialog')]), null)
  assert.equal(chooseWidgetAdapter(action('click', 'Open dialog', null, 'danger'), [descriptor('modal_dialog')]), null)
})

test('normal non-widget elements fall through to existing browser execution', () => {
  const selected = chooseWidgetAdapter(action('click', 'Click ordinary link'), [
    descriptor('combobox', { visible: false }),
  ])
  assert.equal(selected, null)
})
