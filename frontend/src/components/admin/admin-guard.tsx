"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";

import { hasSignedInHint } from "@/lib/auth/session-hint";
import { useCurrentUser } from "@/lib/hooks/use-auth";

/**
 * Gate for the admin area. There is no separate admin login: staff sign in through
 * the very same login page as any customer, and the admin area is simply *hidden*
 * from anyone without access -- never presented as a "you are denied" wall.
 *  - session still resolving -> a neutral loading state;
 *  - not signed in         -> redirect to the shared login (with a return path);
 *  - signed in, not staff   -> redirect home (the area is hidden, not blocked);
 *  - staff                  -> the admin shell.
 *
 * Redirecting safely is subtle: `useCurrentUser` stays *disabled* until the session
 * hint flips (it reads the hint through `useSyncExternalStore`, whose server snapshot
 * is `false` on the first commit), and a disabled query reports `isLoading === false`
 * with no data. So we must not treat "no user yet" as "logged out". Instead the effect
 * reads the hint *directly* -- post-commit `localStorage` is authoritative -- and only
 * redirects to login when there is genuinely no session, or once the probe has resolved.
 * That never bounces a legitimately signed-in staff member on the first tick.
 *
 * This is a UX/visibility gate; the API remains the real authority (every admin
 * endpoint independently enforces staff permission).
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const t = useTranslations("admin");
  const router = useRouter();
  const { data: user, isFetched } = useCurrentUser();

  useEffect(() => {
    // No session at all -> straight to the shared login. Reading the hint here (not
    // during render) avoids the false first-commit snapshot that would bounce staff.
    if (!hasSignedInHint()) {
      router.replace("/login?next=/manage");
      return;
    }
    // A session exists: wait for the probe, then act on its result.
    if (isFetched) {
      if (!user) {
        router.replace("/login?next=/manage");
      } else if (!user.is_staff) {
        router.replace("/");
      }
    }
  }, [user, isFetched, router]);

  if (user?.is_staff) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6 text-muted-foreground">
      {t("guardLoading")}
    </div>
  );
}
