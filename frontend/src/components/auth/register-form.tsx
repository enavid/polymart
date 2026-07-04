"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { SendCodeButton } from "@/components/auth/send-code-button";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { register } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { markSignedIn } from "@/lib/auth/session-hint";

export function RegisterForm() {
  const t = useTranslations("auth");
  const tCommon = useTranslations("common");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      register({
        phone_number: phoneNumber,
        code,
        password,
        full_name: fullName,
        email,
      }),
    // Registration signs the user in (sets the auth cookie), so record the hint
    // that a session exists for the next page they navigate to.
    onSuccess: () => markSignedIn(),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  if (mutation.isSuccess) {
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="success">{t("registerSuccess")}</Alert>
        <Link href="/login" className="text-sm hover:underline">
          {t("haveAccount")}
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">{t("registerTitle")}</h1>
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
          <SendCodeButton phoneNumber={phoneNumber} purpose="registration" />
          <FormField
            id="code"
            label={t("code")}
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <FormField
            id="password"
            label={tCommon("password")}
            type="password"
            autoComplete="new-password"
            hint={t("passwordMinHint")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <FormField
            id="full_name"
            label={t("fullName")}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          <FormField
            id="email"
            label={t("email")}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {mutation.isError ? (
            <Alert variant="destructive">
              {mutation.error instanceof ApiError
                ? mutation.error.detail
                : tCommon("genericError")}
            </Alert>
          ) : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("registerCta")}
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
