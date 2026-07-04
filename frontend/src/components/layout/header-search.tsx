"use client";

import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Product search that lives in the header, right beside the logo. Submitting
 * navigates to the storefront with the term in the URL (`/products?q=…`); the
 * product list reads that param, so the search box and the results stay in sync
 * without shared client state. The field seeds itself from the current `q` so a
 * search term survives a reload of the listing page.
 */
export function HeaderSearch({ className }: { className?: string }) {
  const t = useTranslations("storefront");
  const router = useRouter();
  const params = useSearchParams();
  const [term, setTerm] = useState(() => params.get("q") ?? "");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const query = term.trim();
    router.push(query ? `/products?q=${encodeURIComponent(query)}` : "/products");
  }

  return (
    <form role="search" onSubmit={handleSubmit} className={cn("relative", className)}>
      <Search
        aria-hidden
        className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        type="search"
        aria-label={t("search")}
        placeholder={t("searchPlaceholder")}
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        className="h-9 ps-9"
      />
    </form>
  );
}
