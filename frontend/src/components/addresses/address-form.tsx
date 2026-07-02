"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import type { Address, AddressInput } from "@/lib/api/addresses";

interface AddressFormProps {
  /** When editing, the address being edited (prefills the form). Omit to add a new one. */
  initial?: Address;
  onSubmit: (input: AddressInput) => void;
  onCancel: () => void;
  submitting: boolean;
  errorMessage?: string | null;
}

/** Shared recipient/location form, used to both add and edit an address. */
export function AddressForm({
  initial,
  onSubmit,
  onCancel,
  submitting,
  errorMessage,
}: AddressFormProps) {
  const t = useTranslations("addresses");
  const tCommon = useTranslations("common");
  const [recipientName, setRecipientName] = useState(initial?.recipient_name ?? "");
  const [phoneNumber, setPhoneNumber] = useState(initial?.phone_number ?? "");
  const [province, setProvince] = useState(initial?.province ?? "");
  const [city, setCity] = useState(initial?.city ?? "");
  const [postalCode, setPostalCode] = useState(initial?.postal_code ?? "");
  const [line1, setLine1] = useState(initial?.line1 ?? "");
  const [line2, setLine2] = useState(initial?.line2 ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit({
      recipient_name: recipientName,
      phone_number: phoneNumber,
      province,
      city,
      postal_code: postalCode,
      line1,
      line2: line2 || undefined,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <FormField
        id="recipient_name"
        label={t("recipientName")}
        value={recipientName}
        onChange={(e) => setRecipientName(e.target.value)}
        required
      />
      <FormField
        id="phone_number"
        label={t("phoneNumber")}
        type="tel"
        inputMode="tel"
        dir="ltr"
        value={phoneNumber}
        onChange={(e) => setPhoneNumber(e.target.value)}
        required
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField
          id="province"
          label={t("province")}
          value={province}
          onChange={(e) => setProvince(e.target.value)}
          required
        />
        <FormField
          id="city"
          label={t("city")}
          value={city}
          onChange={(e) => setCity(e.target.value)}
          required
        />
      </div>
      <FormField
        id="postal_code"
        label={t("postalCode")}
        inputMode="numeric"
        dir="ltr"
        value={postalCode}
        onChange={(e) => setPostalCode(e.target.value)}
        required
      />
      <FormField
        id="line1"
        label={t("line1")}
        value={line1}
        onChange={(e) => setLine1(e.target.value)}
        required
      />
      <FormField
        id="line2"
        label={t("line2")}
        value={line2}
        onChange={(e) => setLine2(e.target.value)}
      />
      {errorMessage ? <Alert variant="destructive">{errorMessage}</Alert> : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={submitting}>
          {submitting ? tCommon("loading") : t("save")}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
