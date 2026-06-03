/**
 * Typed wrapper around chrome.runtime.sendMessage.
 * All side panel → service worker communication goes through here.
 *
 * Chrome runtime errors are plain objects, not Error instances.
 * We normalise them here so callers always get a real Error on rejection.
 */
export async function sendToBackground<T>(message: { type: string; [key: string]: unknown }): Promise<T> {
  try {
    const response = await chrome.runtime.sendMessage(message)
    // chrome.runtime.lastError is set for some legacy error paths.
    if (chrome.runtime.lastError) {
      throw new Error(chrome.runtime.lastError.message ?? 'Chrome runtime error')
    }
    return response as T
  } catch (err) {
    // Re-throw with a proper Error so String(err) gives readable text.
    if (err instanceof Error) throw err
    // Chrome extension errors are plain objects: { message: "..." }
    const msg = (err as { message?: string })?.message ?? JSON.stringify(err)
    throw new Error(msg)
  }
}
