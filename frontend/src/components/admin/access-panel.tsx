"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { assignRole, grantChannel } from "@/lib/api/access";
import { ApiError } from "@/lib/api/client";

type AdminT = ReturnType<typeof useTranslations<"admin">>;
type CommonT = ReturnType<typeof useTranslations<"common">>;

/** Map an access error to a localized message; 403 is the common gate failure. */
function errorMessage(
  error: unknown,
  isError: boolean,
  t: AdminT,
  tCommon: CommonT,
): string | null {
  if (error instanceof ApiError) {
    return error.status === 403 ? t("forbidden") : error.detail;
  }
  return isError ? tCommon("genericError") : null;
}

function RoleAssignmentForm() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("");

  const mutation = useMutation({
    mutationFn: () => assignRole(Number(userId), role),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("assignRoleTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <FormField
            id="role_user_id"
            label={t("userId")}
            type="number"
            min={1}
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            required
          />
          <FormField
            id="role_name"
            label={t("role")}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            required
          />
          {mutation.isSuccess ? (
            <Alert variant="success">{t("assignRoleSuccess")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("assignRoleCta")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ChannelGrantForm() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const [userId, setUserId] = useState("");
  const [channelSlug, setChannelSlug] = useState("");

  const mutation = useMutation({
    mutationFn: () => grantChannel(Number(userId), channelSlug),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("grantChannelTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <FormField
            id="grant_user_id"
            label={t("userId")}
            type="number"
            min={1}
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            required
          />
          <FormField
            id="grant_channel_slug"
            label={t("channelSlug")}
            value={channelSlug}
            onChange={(e) => setChannelSlug(e.target.value)}
            required
          />
          {mutation.isSuccess ? (
            <Alert variant="success">{t("grantChannelSuccess")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("grantChannelCta")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function AccessPanel() {
  const t = useTranslations("admin");
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">{t("accessTitle")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("userManagementNote")}
        </p>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <RoleAssignmentForm />
        <ChannelGrantForm />
      </div>
    </div>
  );
}
