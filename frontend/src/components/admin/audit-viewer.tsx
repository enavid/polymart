"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  listAuditEntries,
  type AuditEntry,
  type AuditFilter,
} from "@/lib/api/audit";
import { ApiError } from "@/lib/api/client";
import { formatJalaliDateTime } from "@/lib/format";

function summarizeChanges(entry: AuditEntry): string {
  return Object.entries(entry.changes)
    .map(([field, { before, after }]) => `${field}: ${stringify(before)} → ${stringify(after)}`)
    .join("، "); // Persian comma
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function AuditViewer() {
  const t = useTranslations("audit");
  const tCommon = useTranslations("common");
  const [filter, setFilter] = useState<AuditFilter>({});
  const [draft, setDraft] = useState<{ resource_type: string; action: string; limit: string }>(
    { resource_type: "", action: "", limit: "" },
  );

  const query = useQuery({
    queryKey: ["audit-entries", filter],
    queryFn: () => listAuditEntries(filter),
  });

  function applyFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const limit = Number(draft.limit);
    setFilter({
      resource_type: draft.resource_type || undefined,
      action: draft.action || undefined,
      limit: Number.isFinite(limit) && limit > 0 ? limit : undefined,
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      <form onSubmit={applyFilter} className="grid gap-3 md:grid-cols-4">
        <FormField
          id="filter_resource_type"
          label={t("filterResourceType")}
          value={draft.resource_type}
          onChange={(e) => setDraft({ ...draft, resource_type: e.target.value })}
        />
        <FormField
          id="filter_action"
          label={t("filterAction")}
          value={draft.action}
          onChange={(e) => setDraft({ ...draft, action: e.target.value })}
        />
        <FormField
          id="filter_limit"
          label={t("filterLimit")}
          type="number"
          min={1}
          max={200}
          value={draft.limit}
          onChange={(e) => setDraft({ ...draft, limit: e.target.value })}
        />
        <div className="flex items-end">
          <Button type="submit" variant="outline">
            {t("applyFilter")}
          </Button>
        </div>
      </form>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("noEntries")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("occurredAt")}</TableHead>
              <TableHead>{t("action")}</TableHead>
              <TableHead>{t("resource")}</TableHead>
              <TableHead>{t("actor")}</TableHead>
              <TableHead>{t("changes")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((entry, index) => (
              <TableRow key={`${entry.resource_type}-${entry.resource_id}-${index}`}>
                <TableCell>{formatJalaliDateTime(entry.occurred_at)}</TableCell>
                <TableCell>{entry.action}</TableCell>
                <TableCell>
                  {entry.resource_type}:{entry.resource_id}
                </TableCell>
                <TableCell>{entry.actor ?? t("system")}</TableCell>
                <TableCell className="text-muted-foreground">
                  {summarizeChanges(entry)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
