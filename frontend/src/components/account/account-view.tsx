"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";

function Row({
  label,
  value,
  dir,
}: {
  label: string;
  value: string;
  // Inherently-LTR values (phone, email) keep source order inside the RTL layout.
  dir?: "ltr";
}) {
  return (
    <div className="flex justify-between gap-4 border-b border-border py-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium" dir={dir}>
        {value}
      </span>
    </div>
  );
}

/** A navigation tile linking to one account sub-area. */
function HubTile({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl border border-border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <h3 className="font-semibold text-foreground group-hover:text-primary">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </Link>
  );
}

export function AccountView() {
  const t = useTranslations("account");
  const tCommon = useTranslations("common");
  const tNav = useTranslations("nav");
  const { data: user, isLoading } = useCurrentUser();
  const logout = useLogout();

  if (isLoading) {
    return <p>{tCommon("loading")}</p>;
  }

  if (!user) {
    return (
      <Card className="mx-auto w-full max-w-sm">
        <CardContent className="flex flex-col items-start gap-4 pt-6">
          <p>{t("notLoggedIn")}</p>
          <Link href="/login?next=/account" className="text-primary hover:underline">
            {t("goLogin")}
          </Link>
        </CardContent>
      </Card>
    );
  }

  const greetingName = user.full_name ? `، ${user.full_name}` : "";

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
          <p className="text-muted-foreground">
            {t("greeting", { name: greetingName })}
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          {tNav("logout")}
        </Button>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Profile summary */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>{t("profileTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Row label={t("phoneLabel")} value={user.phone_number} dir="ltr" />
            <Row label={t("nameLabel")} value={user.full_name || "—"} />
            <Row
              label={t("emailLabel")}
              value={user.email || "—"}
              dir={user.email ? "ltr" : undefined}
            />
            <Row label={t("staffLabel")} value={user.is_staff ? t("yes") : t("no")} />
          </CardContent>
        </Card>

        {/* Navigation hub */}
        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          <HubTile
            href="/orders"
            title={t("hubOrders")}
            description={t("hubOrdersDesc")}
          />
          <HubTile
            href="/addresses"
            title={t("hubAddresses")}
            description={t("hubAddressesDesc")}
          />
          <HubTile
            href="/account/wallet"
            title={t("hubWallet")}
            description={t("hubWalletDesc")}
          />
          {user.is_staff ? (
            <HubTile
              href="/manage"
              title={t("hubAdmin")}
              description={t("hubAdminDesc")}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
