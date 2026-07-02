import { apiGet, apiPost } from "@/lib/api/client";

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

export interface UserAccount {
  id: number;
  phone_number: string;
  full_name: string;
  email: string;
  is_staff: boolean;
  is_active: boolean;
}

export interface UserAccountPage {
  count: number;
  limit: number;
  offset: number;
  results: UserAccount[];
}

export function listUsers(params?: {
  limit?: number;
  offset?: number;
}): Promise<UserAccountPage> {
  const query = new URLSearchParams();
  if (params?.limit != null) query.set("limit", String(params.limit));
  if (params?.offset != null) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<UserAccountPage>(`/access/users/${suffix}`);
}

export interface CreateUserInput {
  phone_number: string;
  password: string;
  full_name?: string;
  email?: string;
  is_staff?: boolean;
}

export function createUser(input: CreateUserInput): Promise<UserAccount> {
  return apiPost<UserAccount>("/access/users/", input);
}
