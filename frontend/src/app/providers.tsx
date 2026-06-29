"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/** App-wide client providers (data fetching). Kept thin and client-only. */
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          // The server is the source of truth; don't silently retry mutations
          // or mask auth/permission errors behind retries.
          queries: { retry: false, staleTime: 30_000 },
          mutations: { retry: false },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
