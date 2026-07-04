"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { AccountMenu } from "@/components/layout/account-menu";
import { HeaderSearch } from "@/components/layout/header-search";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";

/**
 * Top navigation: shopping entry points (store, cart) plus a single account
 * entry. Orders and addresses are folded into the account menu so the header
 * stays a shopping surface. Staff additionally get a visible entry into the
 * management area -- surfaced directly (not buried in the account menu) so a
 * signed-in staff member can see and reach it at a glance.
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
      <div className="mx-auto flex w-full max-w-[90rem] items-center justify-between gap-4 px-6 py-3">
        {/* Logo + product search sit together at the start of the bar. */}
        <div className="flex items-center gap-3">
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
          <HeaderSearch className="hidden w-56 md:block lg:w-72" />
        </div>

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

        {/* Trailing utilities: management (staff only) + theme switch + account. */}
        <div className="flex items-center gap-2 border-s border-border ps-3">
          {user?.is_staff ? (
            <Link
              href="/manage"
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              {t("admin")}
            </Link>
          ) : null}
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
