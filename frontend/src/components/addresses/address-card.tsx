"use client";

import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Address } from "@/lib/api/addresses";

interface AddressCardProps {
  address: Address;
  onEdit: () => void;
  onDelete: () => void;
  onConfirmDelete: () => void;
  onCancelDelete: () => void;
  confirmingDelete: boolean;
  deleting: boolean;
  deleteError: string | null;
  onSetDefault: () => void;
  settingDefault: boolean;
}

/** One saved address: its details plus edit/delete/set-default actions. */
export function AddressCard({
  address,
  onEdit,
  onDelete,
  onConfirmDelete,
  onCancelDelete,
  confirmingDelete,
  deleting,
  deleteError,
  onSetDefault,
  settingDefault,
}: AddressCardProps) {
  const t = useTranslations("addresses");

  return (
    <Card data-testid="address-card">
      <CardContent className="flex flex-col gap-2 pt-6">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">{address.recipient_name}</span>
          {address.is_default ? <Badge variant="active">{t("default")}</Badge> : null}
        </div>
        <p className="text-sm text-muted-foreground" dir="ltr">
          {address.phone_number}
        </p>
        {/* Persian comma (matching audit-viewer/product-types-manager display convention) */}
        <p className="text-sm">{`${address.province}، ${address.city}`}</p>
        <p className="text-sm">{address.line1}</p>
        {address.line2 ? <p className="text-sm">{address.line2}</p> : null}
        <p className="text-sm text-muted-foreground" dir="ltr">
          {address.postal_code}
        </p>

        {deleteError ? <Alert variant="destructive">{deleteError}</Alert> : null}

        <div className="mt-2 flex flex-wrap items-center gap-2">
          {!address.is_default ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onSetDefault}
              disabled={settingDefault}
            >
              {t("setDefault")}
            </Button>
          ) : null}
          <Button type="button" size="sm" variant="outline" onClick={onEdit}>
            {t("edit")}
          </Button>
          {confirmingDelete ? (
            <>
              <span className="text-sm text-muted-foreground">{t("deleteConfirm")}</span>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                onClick={onConfirmDelete}
                disabled={deleting}
              >
                {t("delete")}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={onCancelDelete}>
                {t("cancel")}
              </Button>
            </>
          ) : (
            <Button type="button" size="sm" variant="ghost" onClick={onDelete}>
              {t("delete")}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
