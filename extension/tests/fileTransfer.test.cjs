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
  path.join(root, 'src', 'background', 'file_transfer_metadata.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  buildUploadResult,
  shouldHandleUpload,
} = require(path.join(outDir, 'content', 'file_transfer.js'))
const {
  downloadMetadata,
} = require(path.join(outDir, 'background', 'file_transfer_metadata.js'))

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
