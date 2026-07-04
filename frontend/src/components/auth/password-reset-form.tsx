"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { SendCodeButton } from "@/components/auth/send-code-button";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { resetPassword } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

export function PasswordResetForm() {
  const t = useTranslations("auth");
  const tCommon = useTranslations("common");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      resetPassword({
        phone_number: phoneNumber,
        code,
        new_password: newPassword,
      }),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  if (mutation.isSuccess) {
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="success">{t("resetDone")}</Alert>
        <Link href="/login" className="text-sm hover:underline">
          {t("haveAccount")}
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">{t("resetTitle")}</h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <FormField
            id="phone_number"
            label={tCommon("phoneNumber")}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            required
          />
          <SendCodeButton phoneNumber={phoneNumber} purpose="password_reset" />
          <FormField
            id="code"
            label={t("code")}
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <FormField
            id="new_password"
            label={t("newPassword")}
            type="password"
            autoComplete="new-password"
            hint={t("passwordMinHint")}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          {mutation.isError ? (
            <Alert variant="destructive">
              {mutation.error instanceof ApiError
                ? mutation.error.detail
                : tCommon("genericError")}
            </Alert>
          ) : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("resetCta")}
          </Button>
        <Link
          href="/login"
          className="text-sm text-muted-foreground hover:underline"
        >
          {t("haveAccount")}
        </Link>
      </form>
    </div>
  );
}
