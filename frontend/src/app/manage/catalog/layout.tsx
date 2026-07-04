import type { ReactNode } from "react";

/** Catalog management area. The catalog subsections are navigated from the admin
 *  sidebar (under "Catalog"), so this layout only frames the section content. */
export default function CatalogLayout({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-6">{children}</div>;
}
