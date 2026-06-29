import { apiGet, apiPatch, apiPost, toQuery } from "@/lib/api/client";

export interface Channel {
  id: number;
  slug: string;
  name: string;
  currency: string;
  is_active: boolean;
}

export interface CreateChannelInput {
  slug: string;
  name: string;
  currency: string;
  is_active?: boolean;
}

export function listChannels(activeOnly = false): Promise<Channel[]> {
  return apiGet<Channel[]>(
    `/channels/${toQuery({ active: activeOnly ? "true" : undefined })}`,
  );
}

export function createChannel(input: CreateChannelInput): Promise<Channel> {
  return apiPost<Channel>("/channels/", input);
}

export function getChannel(slug: string): Promise<Channel> {
  return apiGet<Channel>(`/channels/${slug}/`);
}

export function setChannelStatus(
  slug: string,
  isActive: boolean,
): Promise<Channel> {
  return apiPatch<Channel>(`/channels/${slug}/`, { is_active: isActive });
}
