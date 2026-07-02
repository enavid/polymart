"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { AddressForm } from "@/components/addresses/address-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createAddress,
  listMyAddresses,
  type Address,
  type AddressInput,
} from "@/lib/api/addresses";
import { getCart, type Cart } from "@/lib/api/cart";
import { ApiError } from "@/lib/api/client";
import { placeOrder } from "@/lib/api/orders";
import { formatMoneyString } from "@/lib/format";
import { useCurrentUser } from "@/lib/hooks/use-auth";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

const CART_KEY = (channel: string) => ["cart", channel] as const;
const ADDRESSES_KEY = ["addresses"] as const;

type Step = "address" | "review";

/** The multi-step checkout: choose a shipping address, then review and place the order. */
export function CheckoutView() {
  const t = useTranslations("checkout");
  const tCommon = useTranslations("common");
  const channel = STOREFRONT_CHANNEL;
  const queryClient = useQueryClient();
  const router = useRouter();

  const { data: user, isLoading: userLoading } = useCurrentUser();

  const [step, setStep] = useState<Step>("address");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [addingNew, setAddingNew] = useState(false);

  const cartQuery = useQuery({
    queryKey: CART_KEY(channel),
    queryFn: () => getCart(channel),
    enabled: Boolean(user),
  });

  const addressesQuery = useQuery({
    queryKey: ADDRESSES_KEY,
    queryFn: listMyAddresses,
    enabled: Boolean(user),
  });

  const addresses = addressesQuery.data;

  // Preselect the shopper's default address (or the first) once the book loads, so a
  // returning shopper can go straight to review without re-picking every time.
  useEffect(() => {
    if (!addresses || selectedId !== null) return;
    if (addresses.length === 0) return;
    const preferred = addresses.find((a) => a.is_default) ?? addresses[0];
    setSelectedId(preferred.id);
  }, [addresses, selectedId]);

  const create = useMutation({
    mutationFn: (input: AddressInput) => createAddress(input),
    onSuccess: (address) => {
      queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY });
      setSelectedId(address.id);
      setAddingNew(false);
    },
  });

  const place = useMutation({
    mutationFn: (addressId: string) => placeOrder(channel, addressId),
    onSuccess: (order) => {
      // The cart is now consumed; drop the cached copy so a revisit refetches the
      // (empty) cart rather than showing stale lines.
      queryClient.removeQueries({ queryKey: CART_KEY(channel) });
      router.push(`/orders/${order.number}`);
    },
  });

  if (userLoading) {
    return <p>{tCommon("loading")}</p>;
  }

  if (!user) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Alert>{t("loginRequired")}</Alert>
        <Link href="/login" className="text-sm text-primary hover:underline">
          {t("goLogin")}
        </Link>
      </div>
    );
  }

  if (cartQuery.isLoading || addressesQuery.isLoading) {
    return <p>{tCommon("loading")}</p>;
  }

  if (cartQuery.isError || addressesQuery.isError) {
    const err = cartQuery.error ?? addressesQuery.error;
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Alert variant="destructive">
          {err instanceof ApiError ? err.detail : t("loadError")}
        </Alert>
      </div>
    );
  }

  const cart = cartQuery.data;
  const hasUnavailable = (cart?.items ?? []).some((line) => !line.available);

  if (cart && cart.items.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground">{t("emptyCart")}</p>
        <Link href="/products" className="text-sm text-primary hover:underline">
          {t("continueShopping")}
        </Link>
      </div>
    );
  }

  const selected = (addresses ?? []).find((a) => a.id === selectedId) ?? null;
  const showForm = addingNew || (addresses ?? []).length === 0;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      {hasUnavailable ? <Alert variant="destructive">{t("unavailableBlocked")}</Alert> : null}

      {step === "address" ? (
        <AddressStep
          addresses={addresses ?? []}
          selectedId={selectedId}
          onSelect={setSelectedId}
          showForm={showForm}
          onAddNew={() => setAddingNew(true)}
          onCancelAdd={
            // With saved addresses, cancel returns to the list; with none, there is no
            // list to return to, so cancel goes back to the cart (checkout needs an
            // address, so an empty-book shopper must add one or leave).
            (addresses ?? []).length > 0
              ? () => setAddingNew(false)
              : () => router.push("/cart")
          }
          onCreate={(input) => create.mutate(input)}
          creating={create.isPending}
          createError={create.isError ? t("addressError") : null}
          canContinue={selected !== null && !hasUnavailable && !showForm}
          onContinue={() => setStep("review")}
        />
      ) : null}

      {step === "review" && selected && cart ? (
        <ReviewStep
          address={selected}
          cart={cart}
          onBack={() => setStep("address")}
          onPlace={() => place.mutate(selected.id)}
          placing={place.isPending}
          placeError={place.isError ? t("placeError") : null}
          blocked={hasUnavailable}
        />
      ) : null}
    </div>
  );
}

interface AddressStepProps {
  addresses: Address[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  showForm: boolean;
  onAddNew: () => void;
  onCancelAdd?: () => void;
  onCreate: (input: AddressInput) => void;
  creating: boolean;
  createError: string | null;
  canContinue: boolean;
  onContinue: () => void;
}

function AddressStep({
  addresses,
  selectedId,
  onSelect,
  showForm,
  onAddNew,
  onCancelAdd,
  onCreate,
  creating,
  createError,
  canContinue,
  onContinue,
}: AddressStepProps) {
  const t = useTranslations("checkout");
  const tAddr = useTranslations("addresses");

  return (
    <div className="flex flex-col gap-4">
      <h2 className="font-medium">{t("addressStepTitle")}</h2>

      {addresses.length === 0 && !showForm ? (
        <p className="text-muted-foreground">{t("noAddresses")}</p>
      ) : null}

      {!showForm ? (
        <>
          <fieldset className="flex flex-col gap-3">
            <legend className="sr-only">{t("chooseAddress")}</legend>
            {addresses.map((address) => (
              <label
                key={address.id}
                className="flex cursor-pointer items-start gap-3 rounded-xl border border-border p-4"
              >
                <input
                  type="radio"
                  name="shipping_address"
                  className="mt-1"
                  value={address.id}
                  checked={selectedId === address.id}
                  onChange={() => onSelect(address.id)}
                />
                <span className="flex flex-col gap-1 text-sm">
                  <span className="flex items-center gap-2 font-medium">
                    {address.recipient_name}
                    {address.is_default ? (
                      <Badge variant="active">{tAddr("default")}</Badge>
                    ) : null}
                  </span>
                  <span dir="ltr" className="text-muted-foreground">
                    {address.phone_number}
                  </span>
                  <span>{`${address.province}، ${address.city}`}</span>
                  <span>{address.line1}</span>
                  {address.line2 ? <span>{address.line2}</span> : null}
                  <span dir="ltr" className="text-muted-foreground">
                    {address.postal_code}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>
          <div className="flex items-center justify-between">
            <Button type="button" variant="outline" onClick={onAddNew}>
              {t("addNewAddress")}
            </Button>
            <Button type="button" onClick={onContinue} disabled={!canContinue}>
              {t("continue")}
            </Button>
          </div>
        </>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <AddressForm
              onSubmit={onCreate}
              onCancel={onCancelAdd ?? (() => undefined)}
              submitting={creating}
              errorMessage={createError}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

interface ReviewStepProps {
  address: Address;
  cart: Cart;
  onBack: () => void;
  onPlace: () => void;
  placing: boolean;
  placeError: string | null;
  blocked: boolean;
}

function ReviewStep({ address, cart, onBack, onPlace, placing, placeError, blocked }: ReviewStepProps) {
  const t = useTranslations("checkout");
  const tCart = useTranslations("cart");

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-medium">{t("reviewStepTitle")}</h2>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-muted-foreground">{t("shipTo")}</h3>
        <Card>
          <CardContent className="flex flex-col gap-1 pt-6 text-sm">
            <span className="font-medium">{address.recipient_name}</span>
            <span dir="ltr" className="text-muted-foreground">
              {address.phone_number}
            </span>
            <span>{`${address.province}، ${address.city}`}</span>
            <span>{address.line1}</span>
            {address.line2 ? <span>{address.line2}</span> : null}
            <span dir="ltr" className="text-muted-foreground">
              {address.postal_code}
            </span>
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-muted-foreground">{t("orderSummary")}</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{tCart("product")}</TableHead>
              <TableHead className="text-left">{tCart("lineTotal")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cart.items.map((line) => (
              <TableRow key={line.sku}>
                <TableCell className="font-medium">
                  {line.sku} × {line.quantity}
                </TableCell>
                <TableCell className="text-left">
                  {formatMoneyString(line.line_total, cart.currency)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="flex items-center justify-between border-t border-border pt-4">
          <span className="font-medium">{tCart("total")}</span>
          <span className="text-lg font-semibold">
            {formatMoneyString(cart.total, cart.currency)}
          </span>
        </div>
      </section>

      {placeError ? <Alert variant="destructive">{placeError}</Alert> : null}

      <div className="flex items-center justify-between">
        <Button type="button" variant="outline" onClick={onBack} disabled={placing}>
          {t("back")}
        </Button>
        <Button type="button" onClick={onPlace} disabled={placing || blocked}>
          {placing ? t("placing") : t("placeOrder")}
        </Button>
      </div>
    </div>
  );
}
