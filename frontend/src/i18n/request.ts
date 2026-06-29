import { getRequestConfig } from "next-intl/server";

import messages from "./messages/fa.json";

// The storefront's primary market is Iran, so Persian is the only locale today.
// next-intl is wired now so adding locales later is configuration, not a rewrite.
export const locale = "fa";

export default getRequestConfig(async () => ({
  locale,
  messages,
}));
