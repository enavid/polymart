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
    // `items-start` keeps the button its natural width (a flex column would
    // otherwise stretch it to look like a disabled input field).
    <div className="flex flex-col items-start gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
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
