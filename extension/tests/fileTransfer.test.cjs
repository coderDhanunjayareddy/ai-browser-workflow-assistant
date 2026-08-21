const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'file-transfer-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'file_transfer.ts'),
  path.join(root, 'src', 'content', 'content_insertion_broker.ts'),
  path.join(root, 'src', 'background', 'file_transfer_metadata.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  buildUploadResult,
  shouldHandleUpload,
} = require(path.join(outDir, 'content', 'file_transfer.js'))
const {
  downloadMetadata,
} = require(path.join(outDir, 'background', 'file_transfer_metadata.js'))
const {
  validateContentInsertion,
} = require(path.join(outDir, 'content', 'content_insertion_broker.js'))

function action(overrides = {}) {
  return {
    action_id: 'upload-1',
    action_type: overrides.action_type ?? 'click',
    target_selector: overrides.target_selector ?? '#file',
    value: overrides.value ?? null,
    description: overrides.description ?? 'Upload resume file',
    reasoning: overrides.reasoning ?? 'The user asked to upload a file.',
    safety_level: overrides.safety_level ?? 'safe',
  }
}

function descriptor(overrides = {}) {
  return {
    supported: true,
    selector: overrides.selector ?? '#file',
    hidden: overrides.hidden ?? false,
    files_count: overrides.files_count ?? 0,
    filename: overrides.filename ?? null,
    backed_by_file_input: overrides.backed_by_file_input ?? true,
  }
}

test('visible file input activates upload without fabricating file contents', () => {
  const result = buildUploadResult(action(), descriptor({ hidden: false }))

  assert.equal(result.upload_attempted, true)
  assert.equal(result.upload_completed, false)
  assert.equal(result.filename, null)
  assert.equal(result.upload_target_selector, '#file')
  assert.equal(result.upload_requires_user_file_selection, true)
  assert.equal(result.upload_accepted, false)
})

test('hidden file input can be activated through backed control metadata', () => {
  const result = buildUploadResult(action({ target_selector: 'label[for="resume"]' }), descriptor({ hidden: true }))

  assert.equal(result.upload_attempted, true)
  assert.equal(result.upload_completed, false)
})

test('drag-and-drop zone backed by file input is recognized as upload-capable', () => {
  const result = buildUploadResult(
    action({ target_selector: '[data-testid="dropzone"]', description: 'Attach file using upload drop zone' }),
    descriptor({ selector: '[data-testid="dropzone"]', backed_by_file_input: true }),
  )

  assert.equal(result.upload_attempted, true)
  assert.equal(result.upload_completed, false)
})

test('upload verification reports selected filename when file is already present', () => {
  const result = buildUploadResult(action(), descriptor({ files_count: 1, filename: 'resume.pdf' }))

  assert.equal(result.success, true)
  assert.equal(result.upload_completed, true)
  assert.equal(result.filename, 'resume.pdf')
  assert.equal(result.upload_files_count, 1)
  assert.equal(result.upload_requires_user_file_selection, false)
  assert.equal(result.upload_accepted, true)
})

test('non-upload and destructive upload actions are ignored', () => {
  assert.equal(shouldHandleUpload(action({ description: 'Click normal button', reasoning: 'Normal click.' }), descriptor()), false)
  assert.equal(shouldHandleUpload(action({ description: 'Upload then submit payment', safety_level: 'safe' }), descriptor()), false)
  assert.equal(shouldHandleUpload(action({ description: 'Upload file', safety_level: 'danger' }), descriptor()), false)
})

test('download completion metadata captures filename, mime, size and path reference', () => {
  const metadata = downloadMetadata({
    filename: 'C:\\Users\\me\\Downloads\\invoice.pdf',
    mime: 'application/pdf',
    fileSize: 12345,
  }, true)

  assert.equal(metadata.download_detected, true)
  assert.equal(metadata.download_completed, true)
  assert.equal(metadata.filename, 'invoice.pdf')
  assert.equal(metadata.mime_type, 'application/pdf')
  assert.equal(metadata.size_bytes, 12345)
  assert.match(metadata.download_path_ref, /invoice\.pdf$/)
})

test('failed download metadata preserves detection and failure status', () => {
  const metadata = downloadMetadata({
    filename: '/tmp/report.csv',
    mime: 'text/csv',
    fileSize: -1,
  }, false)

  assert.equal(metadata.download_detected, true)
  assert.equal(metadata.download_completed, false)
  assert.equal(metadata.filename, 'report.csv')
  assert.equal(metadata.mime_type, 'text/csv')
  assert.equal(metadata.size_bytes, null)
})

function insertionFixture(overrides = {}) {
  const now = 1_800_000_000_000
  const request = {
    request_id: 'insert-1',
    kind: 'document',
    destination_origin: 'https://messaging.example.test',
    destination_entity: 'Synthetic Recipient',
    idempotency_key: 'insert-once-1',
    expected_effect: 'preview_then_send',
    approved_binding_id: 'binding-1',
    confirmation_token: null,
    ...overrides.request,
  }
  const binding = {
    binding_id: 'binding-1',
    kind: 'document',
    filename: 'synthetic-day4.pdf',
    mime_type: 'application/pdf',
    size_bytes: 128,
    content_sha256: 'a'.repeat(64),
    destination_origin: 'https://messaging.example.test',
    destination_entity: 'Synthetic Recipient',
    idempotency_key: 'insert-once-1',
    approved_at_ms: now - 1000,
    expires_at_ms: now + 60_000,
    synthetic: true,
    ...overrides.binding,
  }
  const capability = {
    kind: 'document',
    effect: 'preview_then_send',
    selector: 'input[type=file]',
    backed_by_file_input: true,
    accepted_mime_types: ['application/pdf'],
    multiple: false,
    ...overrides.capability,
  }
  const reservation = {
    chooser_count: 0,
    consumed: false,
    effect_uncertain: false,
    observed_origin: 'https://messaging.example.test/thread/1',
    ...overrides.reservation,
  }
  return { request, binding, capability, reservation, now }
}

test('generic broker accepts one exact synthetic file binding for the observed origin and entity', () => {
  const value = insertionFixture()
  assert.deepEqual(
    validateContentInsertion(value.request, value.binding, value.capability, value.reservation, value.now),
    { allowed: true, requires_confirmation: false, reason: 'approved_file_binding_verified' },
  )
})

test('generic broker blocks path substitution, stale grants, cross-origin reuse and second chooser', () => {
  for (const value of [
    insertionFixture({ request: { approved_binding_id: 'other-binding' } }),
    insertionFixture({ binding: { expires_at_ms: 1_799_999_999_999 } }),
    insertionFixture({ reservation: { observed_origin: 'https://other.example.test' } }),
    insertionFixture({ reservation: { chooser_count: 1 } }),
  ]) {
    const decision = validateContentInsertion(value.request, value.binding, value.capability, value.reservation, value.now)
    assert.equal(decision.allowed, false)
  }
})

test('selection that sends immediately requires confirmation before selecting content', () => {
  const value = insertionFixture({
    request: {
      kind: 'gif',
      expected_effect: 'selection_sends_immediately',
      approved_binding_id: null,
    },
    capability: {
      kind: 'gif',
      effect: 'selection_sends_immediately',
      backed_by_file_input: false,
      accepted_mime_types: [],
    },
  })
  assert.deepEqual(
    validateContentInsertion(value.request, null, value.capability, value.reservation, value.now),
    { allowed: false, requires_confirmation: true, reason: 'confirmation_required_before_selection' },
  )
  value.request.confirmation_token = 'confirmed-once'
  assert.equal(validateContentInsertion(value.request, null, value.capability, value.reservation, value.now).allowed, true)
})

test('uncertain insertion effect blocks retry for every content kind', () => {
  const value = insertionFixture({ reservation: { effect_uncertain: true } })
  assert.deepEqual(
    validateContentInsertion(value.request, value.binding, value.capability, value.reservation, value.now),
    { allowed: false, requires_confirmation: false, reason: 'uncertain_effect_blocks_retry' },
  )
})
