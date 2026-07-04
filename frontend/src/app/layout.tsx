import "@fontsource/vazirmatn/400.css";
import "@fontsource/vazirmatn/500.css";
import "@fontsource/vazirmatn/700.css";
import "./globals.css";

import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { Providers } from "@/app/providers";

export const metadata: Metadata = {
  title: "Polymart",
  description: "White-label, multi-niche e-commerce platform.",
};

// Runs before first paint to set the light/dark palette from the saved choice
// (or the OS preference), so there is no flash of the wrong theme on load. Kept
// in sync with `src/lib/theme/theme.ts`; intentionally tiny and dependency-free.
const THEME_BOOT_SCRIPT = `(function(){try{var c=localStorage.getItem("pm-theme");if(c!=="light"&&c!=="dark"&&c!=="system")c="system";var d=c==="dark"||(c==="system"&&window.matchMedia("(prefers-color-scheme: dark)").matches);var r=document.documentElement;r.classList.add(d?"dark":"light");r.style.colorScheme=d?"dark":"light";}catch(e){}})();`;

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  // Persian / RTL is the default; per-tenant themes may override this in Phase 8.
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} dir="rtl" suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="flex min-h-screen flex-col bg-background text-foreground antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>
            <SiteHeader />
            <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
            <SiteFooter />
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
