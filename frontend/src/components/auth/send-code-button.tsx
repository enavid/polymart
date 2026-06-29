"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { requestOtp, type OtpPurpose } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

interface SendCodeButtonProps {
  phoneNumber: string;
  purpose: OtpPurpose;
}

/** Requests an OTP for the given phone/purpose. Shared by register and reset. */
export function SendCodeButton({ phoneNumber, purpose }: SendCodeButtonProps) {
  const t = useTranslations("auth");
  const tCommon = useTranslations("common");
  const mutation = useMutation({
    mutationFn: () => requestOtp(phoneNumber, purpose),
  });

  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="outline"
        onClick={() => mutation.mutate()}
        disabled={phoneNumber.length === 0 || mutation.isPending}
      >
        {t("otpCta")}
      </Button>
      {mutation.isSuccess ? (
        <Alert variant="success">{t("otpSent")}</Alert>
      ) : null}
      {mutation.isError ? (
        <Alert variant="destructive">
          {mutation.error instanceof ApiError
            ? mutation.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}
    </div>
  );
}
