import Link from "next/link";
import { getTranslations } from "next-intl/server";

/** One footer link column: a heading and a short list of internal links. */
function FooterColumn({
  heading,
  links,
}: {
  heading: string;
  links: { href: string; label: string }[];
}) {
  return (
    <nav aria-label={heading} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-foreground">{heading}</h2>
      <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
        {links.map((link) => (
          <li key={link.href}>
            <Link href={link.href} className="transition-colors hover:text-foreground">
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * Site-wide footer: a brand column, real link columns (shop + account), a
 * trust/assurance column, and a bottom copyright bar. The band spans the full
 * viewport width; its content is held in the same container as the header so the
 * two align. Links point only to routes that exist, so nothing 404s.
 */
export async function SiteFooter() {
  const t = await getTranslations("footer");
  const tCommon = await getTranslations("common");
  const year = new Date().getFullYear();

  const shopLinks = [
    { href: "/products", label: t("allProducts") },
    { href: "/cart", label: t("cart") },
  ];
  const accountLinks = [
    { href: "/account", label: t("account") },
    { href: "/orders", label: t("orders") },
    { href: "/addresses", label: t("addresses") },
  ];
  const trustPoints = [
    t("trustFastShipping"),
    t("trustSecurePayment"),
    t("trustReturns"),
    t("trustSupport"),
  ];

  return (
    <footer className="border-t border-border bg-card/40">
      <div className="mx-auto w-full max-w-[90rem] px-6 py-12">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {/* Brand column */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-lg font-bold tracking-tight text-foreground">
              <span
                aria-hidden
                className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-sm font-black text-primary-foreground"
              >
                پ
              </span>
              {tCommon("appName")}
            </div>
            <p className="max-w-xs text-sm text-muted-foreground">{t("blurb")}</p>
          </div>

          <FooterColumn heading={t("shopHeading")} links={shopLinks} />
          <FooterColumn heading={t("accountHeading")} links={accountLinks} />

          {/* Trust / assurance column (informational, not links). */}
          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-foreground">{t("trustHeading")}</h2>
            <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
              {trustPoints.map((point) => (
                <li key={point} className="flex items-center gap-2">
                  <span aria-hidden className="text-primary">
                    ✓
                  </span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-border pt-6 text-sm text-muted-foreground">
          © {year} {tCommon("appName")} — {t("rights")}
        </div>
      </div>
    </footer>
  );
}
