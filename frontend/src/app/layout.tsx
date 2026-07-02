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

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  // Persian / RTL is the default; per-tenant themes may override this in Phase 8.
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} dir="rtl">
      <body className="flex min-h-screen flex-col bg-background text-foreground antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>
            <SiteHeader />
            <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
            <SiteFooter />
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
