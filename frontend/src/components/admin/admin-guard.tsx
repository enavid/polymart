"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { buttonVariants } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/hooks/use-auth";

/**
 * Gate for the admin area. The admin shell must never render for a visitor who
 * is not a signed-in staff member:
 *  - session still resolving -> a neutral loading state;
 *  - not signed in  -> a sign-in prompt (link into login with a return path);
 *  - signed in, not staff -> a plain "forbidden" page, not the panel;
 *  - staff -> the admin shell.
 *
 * The not-signed-in state is a rendered prompt rather than an imperative redirect
 * on purpose: the session hint resolves via `useSyncExternalStore` (false on the
 * hydration tick, then its real value), so an eager `router.replace` would bounce
 * even a legitimately signed-in staff member on the first commit. Rendering a
 * prompt self-heals as the hint settles, exactly like the account page.
 *
 * This is a UX/visibility gate; the API remains the real authority (every admin
 * endpoint independently enforces staff permission).
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const t = useTranslations("admin");
  const { data: user, isLoading } = useCurrentUser();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-muted-foreground">
        {t("guardLoading")}
      </div>
    );
  }

  if (!user) {
    return (
      <GuardNotice message={t("guardSignIn")}>
        <Link
          href="/login?next=/admin"
          className={buttonVariants({ variant: "default" })}
        >
          {t("guardSignInCta")}
        </Link>
      </GuardNotice>
    );
  }

  if (!user.is_staff) {
    return (
      <GuardNotice message={t("guardForbidden")}>
        <Link href="/" className={buttonVariants({ variant: "outline" })}>
          {t("backToStore")}
        </Link>
      </GuardNotice>
    );
  }

  return <>{children}</>;
}

function GuardNotice({ message, children }: { message: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-lg font-medium">{message}</p>
      {children}
    </div>
  );
}
