"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { SiteHeader } from "@/components/layout/site-header";

/**
 * Chooses the chrome for the current route. The storefront gets the shopper
 * header, a centered content column, and the footer; the admin area (`/admin/*`)
 * gets none of that — it renders its own full-width shell (sidebar + admin top
 * bar) so it never inherits the shopper header, login button, or footer.
 *
 * The footer is a server component, so it is passed in as an already-rendered
 * node rather than imported here (this file is a client component).
 */
export function AppShell({
  children,
  footer,
}: {
  children: ReactNode;
  footer: ReactNode;
}) {
  const pathname = usePathname();
  if (pathname?.startsWith("/admin")) {
    return <>{children}</>;
  }
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
      {footer}
    </>
  );
}
