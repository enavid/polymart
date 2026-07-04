import { getTranslations } from "next-intl/server";

import { Loading } from "@/components/ui/spinner";

/**
 * Route-level fallback shown while a `/manage/*` page is being prepared, so
 * clicking a sidebar section gives immediate feedback (a spinner) instead of a
 * frozen-looking pause during the transition.
 */
export default async function ManageLoading() {
  const tCommon = await getTranslations("common");
  return <Loading label={tCommon("loading")} />;
}
