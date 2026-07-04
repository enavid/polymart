"use client";

import { useMutation } from "@tanstack/react-query";
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
import { ApiError } from "@/lib/api/client";
import { createManualOrder, type ManualOrderInput } from "@/lib/api/orders";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

interface LineDraft {
  sku: string;
  quantity: string;
}

const EMPTY_LINE: LineDraft = { sku: "", quantity: "1" };

/**
 * Staff form to create a manual order (a pre-invoice): channel, one or more line rows
 * (sku + quantity), and the customer's shipping address captured inline. On success it
 * navigates to the printable pre-invoice. The backend is the source of truth for prices,
 * stock, and totals -- this form never computes money.
 */
export function ManualOrderForm() {
  const t = useTranslations("manualOrder");
  const tAddr = useTranslations("addresses");
  const tCommon = useTranslations("common");
  const router = useRouter();

  const [channel, setChannel] = useState(STOREFRONT_CHANNEL);
  const [lines, setLines] = useState<LineDraft[]>([{ ...EMPTY_LINE }]);
  const [recipientName, setRecipientName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [province, setProvince] = useState("");
  const [city, setCity] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [line1, setLine1] = useState("");
  const [line2, setLine2] = useState("");

  const mutation = useMutation({
    mutationFn: (input: ManualOrderInput) => createManualOrder(input),
    onSuccess: (order) => {
      router.push(`/manage/orders/${order.number}/pre-invoice`);
    },
  });

  function setLine(index: number, patch: Partial<LineDraft>) {
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  function addLine() {
    setLines((current) => [...current, { ...EMPTY_LINE }]);
  }

  function removeLine(index: number) {
    setLines((current) => current.filter((_, i) => i !== index));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({
      channel,
      items: lines.map((line) => ({ sku: line.sku, quantity: Number(line.quantity) })),
      shipping_address: {
        recipient_name: recipientName,
        phone_number: phoneNumber,
        province,
        city,
        postal_code: postalCode,
        line1,
        line2: line2 || undefined,
      },
    });
  }

  // The backend validation error is technical/English; show a localized message
  // (mirroring the checkout/address-form pattern).
  const errorMessage =
    mutation.error instanceof ApiError || mutation.isError ? t("error") : null;

  return (
    <Card className="mx-auto w-full max-w-2xl">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-muted-foreground">{t("description")}</p>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <FormField
            id="channel"
            label={t("channel")}
            dir="ltr"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            required
          />

          <fieldset className="flex flex-col gap-3">
            <legend className="mb-1 font-medium">{t("items")}</legend>
            {lines.map((line, index) => (
              <div key={index} className="flex items-end gap-2">
                <div className="grow">
                  <FormField
                    id={`sku_${index}`}
                    label={t("sku")}
                    dir="ltr"
                    value={line.sku}
                    onChange={(e) => setLine(index, { sku: e.target.value })}
                    required
                  />
                </div>
                <div className="w-24">
                  <FormField
                    id={`qty_${index}`}
                    label={t("quantity")}
                    type="number"
                    inputMode="numeric"
                    min={1}
                    value={line.quantity}
                    onChange={(e) => setLine(index, { quantity: e.target.value })}
                    required
                  />
                </div>
                {lines.length > 1 ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => removeLine(index)}
                    aria-label={t("removeItem")}
                  >
                    ×
                  </Button>
                ) : null}
              </div>
            ))}
            <div>
              <Button type="button" variant="outline" onClick={addLine}>
                {t("addItem")}
              </Button>
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-4">
            <legend className="mb-1 font-medium">{t("shippingAddress")}</legend>
            <FormField
              id="recipient_name"
              label={tAddr("recipientName")}
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              required
            />
            <FormField
              id="phone_number"
              label={tAddr("phoneNumber")}
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
                label={tAddr("province")}
                value={province}
                onChange={(e) => setProvince(e.target.value)}
                required
              />
              <FormField
                id="city"
                label={tAddr("city")}
                value={city}
                onChange={(e) => setCity(e.target.value)}
                required
              />
            </div>
            <FormField
              id="postal_code"
              label={tAddr("postalCode")}
              inputMode="numeric"
              dir="ltr"
              value={postalCode}
              onChange={(e) => setPostalCode(e.target.value)}
              required
            />
            <FormField
              id="line1"
              label={tAddr("line1")}
              value={line1}
              onChange={(e) => setLine1(e.target.value)}
              required
            />
            <FormField
              id="line2"
              label={tAddr("line2")}
              value={line2}
              onChange={(e) => setLine2(e.target.value)}
            />
          </fieldset>

          {errorMessage ? <Alert variant="destructive">{errorMessage}</Alert> : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
