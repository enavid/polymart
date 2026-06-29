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

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border py-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
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
          <Link href="/login" className="text-primary hover:underline">
            {t("goLogin")}
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <Row label={t("phoneLabel")} value={user.phone_number} />
          <Row label={t("nameLabel")} value={user.full_name || "—"} />
          <Row label={t("emailLabel")} value={user.email || "—"} />
          <Row
            label={t("staffLabel")}
            value={user.is_staff ? t("yes") : t("no")}
          />
        </div>
        <Button
          variant="outline"
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
        >
          {tNav("logout")}
        </Button>
      </CardContent>
    </Card>
  );
}
