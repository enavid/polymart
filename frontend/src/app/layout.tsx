import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Polymart",
  description: "White-label, multi-niche e-commerce platform.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // Persian / RTL is the default; per-tenant themes may override this.
  return (
    <html lang="fa" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
