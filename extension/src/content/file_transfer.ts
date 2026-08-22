export interface FileTransferAction {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
  content_insertion?: {
    schema_version: 'content_insertion_request.v1'
    request_id: string
    kind: string
    expected_effect: string
    requires_bound_file: boolean
    destination_entity: string
    stage: string
    opens_native_chooser: boolean
    reveal_selector?: string | null
  } | null
}

export interface FileTransferExecutionResult {
  success: boolean
  message: string
  action_id: string
  upload_attempted?: boolean
  upload_completed?: boolean
  filename?: string | null
  upload_target_selector?: string | null
  upload_input_hidden?: boolean
  upload_files_count?: number
  upload_backed_by_file_input?: boolean
  upload_requires_user_file_selection?: boolean
  upload_accepted?: boolean
}

export interface UploadTargetDescriptor {
  supported: boolean
  selector: string | null
  hidden: boolean
  files_count: number
  filename: string | null
  backed_by_file_input: boolean
}

const DESTRUCTIVE_TERMS = [
  'delete',
  'remove',
  'purchase',
  'payment',
  'pay now',
  'place order',
  'checkout',
  'submit',
  'logout',
  'log out',
  'sign out',
  'confirm',
]

export function shouldHandleUpload(action: FileTransferAction, descriptor: UploadTargetDescriptor): boolean {
  if (!descriptor.supported) return false
  if (action.safety_level === 'danger') return false
  const haystack = `${action.description || ''} ${action.reasoning || ''}`.toLowerCase()
  if (!/\b(upload|attach|choose file|select file|file)\b/.test(haystack)) return false
  return !DESTRUCTIVE_TERMS.some((term) => haystack.includes(term))
}

export function buildUploadResult(
  action: FileTransferAction,
  descriptor: UploadTargetDescriptor,
): FileTransferExecutionResult | null {
  if (!shouldHandleUpload(action, descriptor)) return null
  const brokerEvidence = {
    upload_target_selector: descriptor.selector,
    upload_input_hidden: descriptor.hidden,
    upload_files_count: descriptor.files_count,
    upload_backed_by_file_input: descriptor.backed_by_file_input,
    upload_requires_user_file_selection: descriptor.files_count === 0,
    upload_accepted: descriptor.files_count > 0,
  }
  if (descriptor.files_count > 0) {
    return {
      success: true,
      message: `File upload already selected: ${descriptor.filename || 'file'}`,
      action_id: action.action_id,
      upload_attempted: true,
      upload_completed: true,
      filename: descriptor.filename,
      ...brokerEvidence,
    }
  }
  return {
    success: true,
    message: 'Activated file upload control. Waiting for user-selected file.',
    action_id: action.action_id,
    upload_attempted: true,
    upload_completed: false,
    filename: null,
    ...brokerEvidence,
  }
}

export function detectUploadTarget(action: FileTransferAction): UploadTargetDescriptor {
  function safeQuery(selector: string | null): Element | null {
    if (!selector) return null
    try {
      return document.querySelector(selector)
    } catch {
      return null
    }
  }

  function visible(candidate: Element | null): boolean {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function descriptorFor(input: HTMLInputElement | null, selector: string | null): UploadTargetDescriptor {
    if (!input) {
      return { supported: false, selector, hidden: false, files_count: 0, filename: null, backed_by_file_input: false }
    }
    const files = input.files ? Array.from(input.files) : []
    return {
      supported: true,
      selector,
      hidden: !visible(input),
      files_count: files.length,
      filename: files[0]?.name ?? null,
      backed_by_file_input: true,
    }
  }

  const direct = safeQuery(action.target_selector)
  if (direct instanceof HTMLInputElement && direct.type === 'file') {
    return descriptorFor(direct, action.target_selector)
  }

  if (direct instanceof HTMLLabelElement) {
    const control = direct.control
    if (control instanceof HTMLInputElement && control.type === 'file') {
      return descriptorFor(control, action.target_selector)
    }
  }

  if (direct instanceof HTMLElement) {
    const nested = direct.querySelector('input[type="file"]')
    if (nested instanceof HTMLInputElement) return descriptorFor(nested, action.target_selector)

    const labelledInput = direct.id
      ? document.querySelector(`input[type="file"][id="${direct.id.replace(/"/g, '\\"')}"]`)
      : null
    if (labelledInput instanceof HTMLInputElement) return descriptorFor(labelledInput, action.target_selector)

    const nearbyInput = direct.closest('form, section, div')?.querySelector('input[type="file"]')
    if (nearbyInput instanceof HTMLInputElement) return descriptorFor(nearbyInput, action.target_selector)
  }

  const describedUpload = /\b(upload|attach|choose file|select file|drop file|drag)\b/i.test(
    `${action.description || ''} ${action.value || ''}`,
  )
  if (describedUpload) {
    const firstInput = document.querySelector('input[type="file"]')
    if (firstInput instanceof HTMLInputElement) return descriptorFor(firstInput, 'input[type="file"]')
  }

  return { supported: false, selector: action.target_selector, hidden: false, files_count: 0, filename: null, backed_by_file_input: false }
}

export async function executeUploadHandler(action: FileTransferAction): Promise<FileTransferExecutionResult | null> {
  function safeQuery(selector: string | null): Element | null {
    if (!selector) return null
    try {
      return document.querySelector(selector)
    } catch {
      return null
    }
  }

  function visible(candidate: Element | null): boolean {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function descriptorFor(input: HTMLInputElement | null, selector: string | null): UploadTargetDescriptor {
    if (!input) {
      return { supported: false, selector, hidden: false, files_count: 0, filename: null, backed_by_file_input: false }
    }
    const files = input.files ? Array.from(input.files) : []
    return {
      supported: true,
      selector,
      hidden: !visible(input),
      files_count: files.length,
      filename: files[0]?.name ?? null,
      backed_by_file_input: true,
    }
  }

  function detect(): UploadTargetDescriptor {
    const direct = safeQuery(action.target_selector)
    if (direct instanceof HTMLInputElement && direct.type === 'file') return descriptorFor(direct, action.target_selector)
    if (direct instanceof HTMLLabelElement) {
      const control = direct.control
      if (control instanceof HTMLInputElement && control.type === 'file') return descriptorFor(control, action.target_selector)
    }
    if (direct instanceof HTMLElement) {
      const nested = direct.querySelector('input[type="file"]')
      if (nested instanceof HTMLInputElement) return descriptorFor(nested, action.target_selector)
      const nearbyInput = direct.closest('form, section, div')?.querySelector('input[type="file"]')
      if (nearbyInput instanceof HTMLInputElement) return descriptorFor(nearbyInput, action.target_selector)
    }
    const describedUpload = /\b(upload|attach|choose file|select file|drop file|drag)\b/i.test(
      `${action.description || ''} ${action.value || ''}`,
    )
    if (describedUpload) {
      const firstInput = document.querySelector('input[type="file"]')
      if (firstInput instanceof HTMLInputElement) return descriptorFor(firstInput, 'input[type="file"]')
    }
    return { supported: false, selector: action.target_selector, hidden: false, files_count: 0, filename: null, backed_by_file_input: false }
  }

  function safeAction(): boolean {
    if (action.safety_level === 'danger') return false
    const haystack = `${action.description || ''} ${action.reasoning || ''}`.toLowerCase()
    if (!/\b(upload|attach|choose file|select file|file)\b/.test(haystack)) return false
    return ![
      'delete',
      'remove',
      'purchase',
      'payment',
      'pay now',
      'place order',
      'checkout',
      'submit',
      'logout',
      'log out',
      'sign out',
      'confirm',
    ].some((term) => haystack.includes(term))
  }

  const descriptor = detect()
  if (!safeAction() || !descriptor.supported) return null
  const result = buildUploadResult(action, descriptor)
  if (!result) return null

  const target = descriptor.selector ? document.querySelector(descriptor.selector) : null
  const uploadInput = target instanceof HTMLInputElement && target.type === 'file'
    ? target
    : document.querySelector('input[type="file"]')

  if (uploadInput instanceof HTMLElement && result.upload_completed !== true) {
    uploadInput.click()
  } else if (target instanceof HTMLElement && result.upload_completed !== true) {
    target.click()
  }

  return result
}
