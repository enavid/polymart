import { getTranslations } from "next-intl/server";
import Link from "next/link";
import type { ReactNode } from "react";

export default async function AdminLayout({
  children,
}: {
  children: ReactNode;
}) {
  const t = await getTranslations("nav");
  return (
    <div className="flex flex-col gap-6">
      <nav className="flex gap-4 border-b border-border pb-3 text-sm">
        <Link href="/admin/access" className="hover:underline">
          {t("access")}
        </Link>
        <Link href="/admin/channels" className="hover:underline">
          {t("channels")}
        </Link>
        <Link href="/admin/audit" className="hover:underline">
          {t("audit")}
        </Link>
      </nav>
      {children}
    </div>
  );
}
