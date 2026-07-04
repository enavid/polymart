import { getTranslations } from "next-intl/server";
import Link from "next/link";
import type { ReactNode } from "react";

/** Sub-navigation across the catalog management sections. */
export default async function CatalogLayout({
  children,
}: {
  children: ReactNode;
}) {
  const t = await getTranslations("catalog");
  const links = [
    { href: "/manage/catalog/products", label: t("navProducts") },
    { href: "/manage/catalog/product-types", label: t("navProductTypes") },
    { href: "/manage/catalog/attributes", label: t("navAttributes") },
    { href: "/manage/catalog/categories", label: t("navCategories") },
    { href: "/manage/catalog/collections", label: t("navCollections") },
    { href: "/manage/catalog/import-export", label: t("navImportExport") },
  ];
  return (
    <div className="flex flex-col gap-6">
      <nav className="flex flex-wrap gap-3 border-b border-border pb-3 text-sm">
        {links.map((link) => (
          <Link key={link.href} href={link.href} className="hover:underline">
            {link.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
