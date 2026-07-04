/**
 * Resolve a post-authentication redirect target from an untrusted `next` value
 * (typically a query-string parameter).
 *
 * Only same-origin absolute paths are honoured; anything else falls back to the
 * home page. This closes the classic open-redirect hole where `?next=//evil.com`
 * or `?next=https://evil.com` would bounce a freshly authenticated user off-site.
 */
const HOME = "/";

export function resolveRedirect(next: string | null | undefined): string {
  if (!next) {
    return HOME;
  }
  // Must be an absolute path, and must not be protocol-relative (`//host`) or a
  // backslash-smuggled variant (`/\host`) that browsers normalise to an origin.
  if (!next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return HOME;
  }
  return next;
}
