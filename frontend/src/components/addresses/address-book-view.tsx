"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { AddressCard } from "@/components/addresses/address-card";
import { AddressForm } from "@/components/addresses/address-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  createAddress,
  deleteAddress,
  listMyAddresses,
  setDefaultAddress,
  updateAddress,
  type Address,
  type AddressInput,
} from "@/lib/api/addresses";
import { ApiError } from "@/lib/api/client";
import { useCurrentUser } from "@/lib/hooks/use-auth";

const ADDRESSES_KEY = ["addresses"] as const;

type Mode = { kind: "list" } | { kind: "new" } | { kind: "edit"; address: Address };

/** The shopper's saved address book: list, add, edit, delete, and set default. */
export function AddressBookView() {
  const t = useTranslations("addresses");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);

  const { data: user, isLoading: userLoading } = useCurrentUser();

  const query = useQuery({
    queryKey: ADDRESSES_KEY,
    queryFn: listMyAddresses,
    // The address book lives behind auth; only fetch once we know there is a user.
    enabled: Boolean(user),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY });
  }

  const create = useMutation({
    mutationFn: (input: AddressInput) => createAddress(input),
    onSuccess: () => {
      invalidate();
      setMode({ kind: "list" });
    },
  });

  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: AddressInput }) => updateAddress(id, input),
    onSuccess: () => {
      invalidate();
      setMode({ kind: "list" });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteAddress(id),
    onSuccess: () => {
      invalidate();
      setConfirmingDeleteId(null);
    },
  });

  const setDefault = useMutation({
    mutationFn: (id: string) => setDefaultAddress(id),
    onSuccess: invalidate,
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

  // The backend's field-level detail is technical/English (e.g. an out-of-range raw
  // value with no sentence around it); a shopper-appropriate localized message is
  // shown instead, matching how the cart's checkout error is handled.
  function mapMutationError(error: unknown): string {
    if (error instanceof ApiError) {
      if (error.status === 409) return t("limitExceeded");
      if (error.status === 404) return t("notFound");
      if (error.status === 400) return t("validationError");
    }
    return tCommon("genericError");
  }

  const addresses = query.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError ? query.error.detail : t("loadError")}
        </Alert>
      ) : null}

      {query.data && addresses.length === 0 && mode.kind === "list" ? (
        <p className="text-muted-foreground">{t("empty")}</p>
      ) : null}

      {query.data && mode.kind === "list" && addresses.length > 0 ? (
        <div className="flex flex-col gap-4">
          {addresses.map((address) => (
            <AddressCard
              key={address.id}
              address={address}
              onEdit={() => setMode({ kind: "edit", address })}
              onDelete={() => setConfirmingDeleteId(address.id)}
              onConfirmDelete={() => remove.mutate(address.id)}
              onCancelDelete={() => setConfirmingDeleteId(null)}
              confirmingDelete={confirmingDeleteId === address.id}
              deleting={remove.isPending && confirmingDeleteId === address.id}
              deleteError={
                remove.isError && confirmingDeleteId === address.id
                  ? mapMutationError(remove.error)
                  : null
              }
              onSetDefault={() => setDefault.mutate(address.id)}
              settingDefault={setDefault.isPending}
            />
          ))}
        </div>
      ) : null}

      {mode.kind === "new" ? (
        <Card>
          <CardContent className="pt-6">
            <AddressForm
              onSubmit={(input) => create.mutate(input)}
              onCancel={() => setMode({ kind: "list" })}
              submitting={create.isPending}
              errorMessage={create.isError ? mapMutationError(create.error) : null}
            />
          </CardContent>
        </Card>
      ) : null}

      {mode.kind === "edit" ? (
        <Card>
          <CardContent className="pt-6">
            <AddressForm
              initial={mode.address}
              onSubmit={(input) => update.mutate({ id: mode.address.id, input })}
              onCancel={() => setMode({ kind: "list" })}
              submitting={update.isPending}
              errorMessage={update.isError ? mapMutationError(update.error) : null}
            />
          </CardContent>
        </Card>
      ) : null}

      {mode.kind === "list" ? (
        <Button type="button" variant="outline" onClick={() => setMode({ kind: "new" })}>
          {t("addNew")}
        </Button>
      ) : null}
    </div>
  );
}
