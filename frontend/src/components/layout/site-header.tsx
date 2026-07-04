"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { AccountMenu } from "@/components/layout/account-menu";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";

/**
 * Top navigation: shopping entry points (store, cart) plus a single account
 * entry. Orders, addresses, and the admin panel are folded into the account
 * menu rather than top-level links, so the header stays a shopping surface.
 */
export function SiteHeader() {
  const t = useTranslations("nav");
  const tCommon = useTranslations("common");
  const pathname = usePathname();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  // Send "please sign in" back to the current page after login.
  const loginHref = `/login?next=${encodeURIComponent(pathname || "/")}`;

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
        </nav>

        {/* Trailing utilities: theme switch + account, separated from navigation. */}
        <div className="flex items-center gap-2 border-s border-border ps-3">
          <ThemeToggle />
          {user ? (
            <AccountMenu
              user={user}
              onLogout={() => logout.mutate()}
              loggingOut={logout.isPending}
            />
          ) : (
            <Link href={loginHref} className={linkClass}>
              {t("login")}
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
