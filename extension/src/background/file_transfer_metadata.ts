export interface DownloadItemLike {
  filename?: string
  mime?: string
  fileSize?: number
}

export interface FileTransferMetadata {
  download_detected?: boolean
  download_completed?: boolean
  filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  download_path_ref?: string | null
}

export function downloadMetadata(item: DownloadItemLike | null, completed: boolean): FileTransferMetadata {
  return {
    download_detected: true,
    download_completed: completed,
    filename: item?.filename ? basename(item.filename) : null,
    mime_type: item?.mime || null,
    size_bytes: typeof item?.fileSize === 'number' && item.fileSize >= 0 ? item.fileSize : null,
    download_path_ref: item?.filename || null,
  }
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path
}
