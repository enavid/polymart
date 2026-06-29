import { apiPost } from "@/lib/api/client";

// The Phase 1 access API exposes only role assignment and per-channel grants,
// both keyed by a numeric user id. There is no user create/list endpoint yet
// (users self-register), so the admin UI operates on user ids directly.

export function assignRole(userId: number, role: string): Promise<void> {
  return apiPost<void>("/access/role-assignments/", {
    user_id: userId,
    role,
  });
}

export function grantChannel(
  userId: number,
  channelSlug: string,
): Promise<void> {
  return apiPost<void>("/access/channel-grants/", {
    user_id: userId,
    channel_slug: channelSlug,
  });
}
