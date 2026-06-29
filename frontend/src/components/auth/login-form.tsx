"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { CURRENT_USER_KEY } from "@/lib/hooks/use-auth";

export function LoginForm() {
  const t = useTranslations("auth");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [phoneNumber, setPhoneNumber] = useState("");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: () => login(phoneNumber, password),
    onSuccess: (user) => {
      queryClient.setQueryData(CURRENT_USER_KEY, user);
      router.push("/account");
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  // A 401 is the deliberate, uniform "invalid credentials" response that does
  // not reveal whether the account exists; show the localized uniform message.
  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.status === 401
        ? t("invalidCredentials")
        : mutation.error.detail
      : mutation.isError
        ? tCommon("genericError")
        : null;

  return (
    <Card className="mx-auto w-full max-w-sm">
      <CardHeader>
        <CardTitle>{t("loginTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
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
          <FormField
            id="password"
            label={tCommon("password")}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {errorMessage ? (
            <Alert variant="destructive">{errorMessage}</Alert>
          ) : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("loginCta")}
          </Button>
          <div className="flex justify-between text-sm text-muted-foreground">
            <Link href="/register" className="hover:underline">
              {t("noAccount")}
            </Link>
            <Link href="/password-reset" className="hover:underline">
              {t("forgotPassword")}
            </Link>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
