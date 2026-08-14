export function isGroundedBrowserTarget(url: string | null | undefined): boolean {
  return /^https?:\/\//i.test(url ?? '')
}
