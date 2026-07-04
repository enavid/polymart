"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";

/** Top navigation. Surfaces admin links only to staff users. */
export function SiteHeader() {
  const t = useTranslations("nav");
  const tCommon = useTranslations("common");
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  const linkClass =
    "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground";

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/80 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <Link
          href="/"
          className="flex items-center gap-2 text-lg font-bold tracking-tight text-foreground"
        >
          <span
            aria-hidden
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-sm font-black text-primary-foreground"
          >
            پ
          </span>
          {tCommon("appName")}
        </Link>

        <nav className="flex items-center gap-1">
          <Link href="/products" className={linkClass}>
            {t("storefront")}
          </Link>
          {/* The cart is a first-class storefront entry point for everyone; a guest
              builds and checks out a cart without signing in (guest checkout). */}
          <Link href="/cart" className={linkClass}>
            {t("cart")}
          </Link>
          {user ? (
            <>
              <Link href="/orders" className={linkClass}>
                {t("orders")}
              </Link>
              <Link href="/addresses" className={linkClass}>
                {t("addresses")}
              </Link>
              <Link href="/account" className={linkClass}>
                {t("account")}
              </Link>
              {user.is_staff ? (
                <Link
                  href="/admin"
                  className="rounded-md px-2.5 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-accent"
                >
                  {t("admin")}
                </Link>
              ) : null}
            </>
          ) : null}

          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          <ThemeToggle />

          {user ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
            >
              {t("logout")}
            </Button>
          ) : (
            <Link href="/login" className={linkClass}>
              {t("login")}
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
