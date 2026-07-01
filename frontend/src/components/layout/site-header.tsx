"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";

/** Top navigation. Surfaces admin links only to staff users. */
export function SiteHeader() {
  const t = useTranslations("nav");
  const tCommon = useTranslations("common");
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <header className="border-b border-border">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-lg font-semibold">
          {tCommon("appName")}
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link href="/products" className="px-2 hover:underline">
            {t("storefront")}
          </Link>
          {user ? (
            <>
              <Link href="/cart" className="px-2 hover:underline">
                {t("cart")}
              </Link>
              <Link href="/account" className="px-2 hover:underline">
                {t("account")}
              </Link>
              {user.is_staff ? (
                <Link href="/admin" className="px-2 hover:underline">
                  {t("admin")}
                </Link>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
              >
                {t("logout")}
              </Button>
            </>
          ) : (
            <Link href="/login" className="px-2 hover:underline">
              {t("login")}
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
