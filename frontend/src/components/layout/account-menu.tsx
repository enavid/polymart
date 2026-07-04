"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import type { UserProfile } from "@/lib/api/auth";

interface AccountMenuProps {
  user: UserProfile;
  onLogout: () => void;
  loggingOut: boolean;
}

/**
 * The signed-in user's account entry point in the header: a single trigger that
 * opens a dropdown of account areas (profile, orders, addresses, admin for
 * staff) plus logout. Orders/addresses live here rather than as top-level nav so
 * the header stays a shopping surface and the account is one consolidated hub.
 */
export function AccountMenu({ user, onLogout, loggingOut }: AccountMenuProps) {
  const t = useTranslations("nav");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click or Escape while open.
  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const itemClass =
    "block rounded-md px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent hover:text-accent-foreground";
  const label = user.full_name || t("account");
  const initial = (user.full_name || "؟").trim().charAt(0);

  const links = [
    { href: "/account", label: t("account") },
    { href: "/orders", label: t("orders") },
    { href: "/addresses", label: t("addresses") },
  ];

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-foreground transition-colors hover:bg-accent"
      >
        <span
          aria-hidden
          className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground"
        >
          {initial}
        </span>
        <span className="hidden max-w-[10rem] truncate sm:inline">{label}</span>
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={t("account")}
          className="absolute end-0 top-full z-30 mt-2 w-48 rounded-lg border border-border bg-popover p-1 shadow-lg"
        >
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              role="menuitem"
              className={itemClass}
              onClick={() => setOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          {user.is_staff ? (
            <Link
              href="/admin"
              role="menuitem"
              className={`${itemClass} font-medium text-primary`}
              onClick={() => setOpen(false)}
            >
              {t("admin")}
            </Link>
          ) : null}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            disabled={loggingOut}
            className={`${itemClass} w-full text-start disabled:opacity-50`}
          >
            {t("logout")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
