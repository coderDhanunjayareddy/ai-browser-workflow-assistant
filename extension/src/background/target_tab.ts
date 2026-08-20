export function isGroundedBrowserTarget(url: string | null | undefined): boolean {
  return /^https?:\/\//i.test(url ?? '')
}

export function isSelectableBrowserTarget(url: string | null | undefined): boolean {
  const normalized = (url ?? '').toLowerCase()
  return isGroundedBrowserTarget(normalized)
    || normalized === 'about:blank'
    || normalized === 'chrome://newtab/'
    || normalized === 'chrome://new-tab-page/'
}
