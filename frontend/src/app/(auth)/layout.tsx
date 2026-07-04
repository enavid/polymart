import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";

/**
 * Shared shell for the auth routes (login, register, password reset): a
 * split-screen with a branded gradient panel on one side and the form centered
 * on the other. The brand panel is hidden on small screens so the form gets the
 * full width there — no lonely card floating in an empty page.
 */
export default async function AuthLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("auth");
  const tCommon = await getTranslations("common");
  const points = [t("brandPoint1"), t("brandPoint2"), t("brandPoint3")];

  return (
    <div className="mx-auto grid w-full max-w-5xl overflow-hidden rounded-2xl border border-border bg-card shadow-sm lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between gap-10 bg-[image:linear-gradient(135deg,var(--hero-from),var(--hero-to))] p-10 text-white lg:flex">
        <div className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <span
            aria-hidden
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 text-sm font-black"
          >
            پ
          </span>
          {tCommon("appName")}
        </div>
        <div className="flex flex-col gap-4">
          <h2 className="text-3xl font-bold leading-tight tracking-tight">
            {t("brandHeading")}
          </h2>
          <p className="text-white/85">{t("brandSubtitle")}</p>
          <ul className="mt-2 flex flex-col gap-2.5 text-white/90">
            {points.map((point) => (
              <li key={point} className="flex items-center gap-2">
                <span aria-hidden className="text-white">
                  ✓
                </span>
                {point}
              </li>
            ))}
          </ul>
        </div>
        <span className="text-sm text-white/60">{tCommon("appName")}</span>
      </aside>

      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
