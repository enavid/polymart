import { apiGet, toQuery } from "@/lib/api/client";

export interface FieldChange {
  before: unknown;
  after: unknown;
}

export interface AuditEntry {
  action: string;
  resource_type: string;
  resource_id: string;
  actor: string | null;
  occurred_at: string;
  changes: Record<string, FieldChange>;
}

export interface AuditFilter {
  resource_type?: string;
  action?: string;
  limit?: number;
}

// The backend returns a plain array (newest first), not a paginated envelope;
// `limit` bounds the size (default 50, max 200).
export function listAuditEntries(
  filter: AuditFilter = {},
): Promise<AuditEntry[]> {
  return apiGet<AuditEntry[]>(`/audit/entries/${toQuery({ ...filter })}`);
}
