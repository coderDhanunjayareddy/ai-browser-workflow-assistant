export interface ContentSelectionEvidence {
  success: boolean
  message: string
  content_request_id: string
  content_kind: string
  insertion_effect: string
  destination_origin: string
  destination_entity: string
  upload_files_count: number
  upload_attempted: boolean
  upload_completed: boolean
  upload_backed_by_file_input: boolean
  filename: string | null
  mime_type: string | null
  size_bytes: number | null
  content_sha256: string | null
  preview_identity_observed: boolean
  upload_accepted: boolean
  chooser_cancelled: boolean
}

type PendingContentSelection = Omit<ContentSelectionEvidence, 'success' | 'message' | 'preview_identity_observed'>

type ContentSelectionWindow = typeof globalThis & {
  __aiBrowserContentSelections?: Record<string, PendingContentSelection>
}

export function prepareContentInsertionSelectionInspection(
  declaration: {
    request_id: string
    kind: string
    expected_effect: string
    destination_entity: string
  },
): boolean {
  const runtime = globalThis as ContentSelectionWindow
  runtime.__aiBrowserContentSelections ||= {}
  delete runtime.__aiBrowserContentSelections[declaration.request_id]

  const onChange = async (event: Event) => {
    const input = event.target
    if (!(input instanceof HTMLInputElement) || input.type.toLowerCase() !== 'file') return
    const file = input.files?.[0]
    if (!file) return
    document.removeEventListener('change', onChange, true)
    let contentSha256: string | null = null
    if (file.size <= 25 * 1024 * 1024) {
      const value = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
      contentSha256 = Array.from(new Uint8Array(value)).map((item) => item.toString(16).padStart(2, '0')).join('')
    }
    runtime.__aiBrowserContentSelections![declaration.request_id] = {
      content_request_id: declaration.request_id,
      content_kind: declaration.kind,
      insertion_effect: declaration.expected_effect,
      destination_origin: location.origin,
      destination_entity: declaration.destination_entity,
      upload_files_count: input.files?.length || 0,
      upload_attempted: true,
      upload_completed: true,
      upload_backed_by_file_input: true,
      filename: file.name,
      mime_type: file.type || null,
      size_bytes: file.size,
      content_sha256: contentSha256,
      upload_accepted: true,
      chooser_cancelled: false,
    }
  }
  document.addEventListener('change', onChange, true)
  return true
}

export async function inspectContentInsertionSelection(
  declaration: {
    request_id: string
    kind: string
    expected_effect: string
    destination_entity: string
  },
  timeoutMs = 60_000,
): Promise<ContentSelectionEvidence> {
  const deadline = Date.now() + Math.max(100, Math.min(timeoutMs, 120_000))
  const runtime = globalThis as ContentSelectionWindow
  runtime.__aiBrowserContentSelections ||= {}

  async function digest(file: File): Promise<string | null> {
    // Day 4 live certification is intentionally bounded to small synthetic
    // files. Large-file streaming is a separate adapter capability; do not
    // base64-copy content through planner/backend payloads.
    if (file.size > 25 * 1024 * 1024) return null
    const value = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
    return Array.from(new Uint8Array(value)).map((item) => item.toString(16).padStart(2, '0')).join('')
  }

  while (Date.now() < deadline) {
    let selected = runtime.__aiBrowserContentSelections[declaration.request_id]
    const inputs = Array.from(document.querySelectorAll('input[type="file"]')) as HTMLInputElement[]
    const input = inputs.find((candidate) => (candidate.files?.length || 0) > 0)
    const file = input?.files?.[0] || null
    if (!selected && file) {
      selected = {
        content_request_id: declaration.request_id,
        content_kind: declaration.kind,
        insertion_effect: declaration.expected_effect,
        destination_origin: location.origin,
        destination_entity: declaration.destination_entity,
        upload_files_count: input?.files?.length || 0,
        upload_attempted: true,
        upload_completed: true,
        upload_backed_by_file_input: true,
        filename: file.name,
        mime_type: file.type || null,
        size_bytes: file.size,
        content_sha256: await digest(file),
        upload_accepted: true,
        chooser_cancelled: false,
      }
      runtime.__aiBrowserContentSelections[declaration.request_id] = selected
    }
    if (selected) {
      const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ')
      const previewIdentityObserved = Boolean(selected.filename && bodyText.includes(selected.filename))
      if (!previewIdentityObserved) {
        await new Promise((resolve) => setTimeout(resolve, 150))
        continue
      }
      return {
        success: true,
        message: `Broker-bound content preview verified: ${selected.filename}`,
        ...selected,
        preview_identity_observed: previewIdentityObserved,
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 150))
  }

  const selected = runtime.__aiBrowserContentSelections[declaration.request_id]
  if (selected) {
    return {
      success: false,
      message: `Content was selected, but its exact preview identity was not observed: ${selected.filename}`,
      ...selected,
      preview_identity_observed: false,
    }
  }

  return {
    success: false,
    message: 'No file selection was observed within the bounded chooser window.',
    content_request_id: declaration.request_id,
    content_kind: declaration.kind,
    insertion_effect: declaration.expected_effect,
    destination_origin: location.origin,
    destination_entity: declaration.destination_entity,
    upload_files_count: 0,
    upload_attempted: true,
    upload_completed: false,
    upload_backed_by_file_input: true,
    filename: null,
    mime_type: null,
    size_bytes: null,
    content_sha256: null,
    preview_identity_observed: false,
    upload_accepted: false,
    chooser_cancelled: true,
  }
}
