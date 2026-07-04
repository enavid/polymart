"use client";

import {
  ArrowRight,
  ChevronDown,
  FolderTree,
  Layers,
  LayoutDashboard,
  type LucideIcon,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Receipt,
  ScrollText,
  Shapes,
  SlidersHorizontal,
  Store,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useLogout } from "@/lib/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  Icon: LucideIcon;
}

interface NavGroup {
  heading: string;
  items: NavItem[];
}

/** Whether a nav item is the active section (exact for the dashboard root, prefix
 *  for the rest so sub-pages keep their section highlighted). */
function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) {
    return false;
  }
  return href === "/manage" ? pathname === "/manage" : pathname.startsWith(href);
}

/**
 * The dedicated admin panel shell: a persistent sidebar of grouped sections and
 * an admin top bar with its own identity, a back-to-store link, theme control,
 * and sign-out. Full width — the content area uses all the horizontal space
 * rather than the shopper's centered column. On small screens the sidebar folds
 * into a horizontal scrolling nav under the top bar.
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const t = useTranslations("nav");
  const tAdmin = useTranslations("admin");
  const tCommon = useTranslations("common");
  const tCatalog = useTranslations("catalog");
  const pathname = usePathname();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  // Sidebar sections are collapsible so a long menu can be tidied away; all
  // start expanded, and toggling is remembered for the session.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const toggleGroup = (heading: string) =>
    setCollapsed((state) => ({ ...state, [heading]: !state[heading] }));

  // The whole sidebar can collapse to a slim icon rail to reclaim horizontal
  // space; in that state group headings give way to a flat, icon-only nav.
  const [railed, setRailed] = useState(false);

  // Grouped by concern so the panel stays coherent as it grows: overview,
  // catalog (with its import/export sub-tool), sales, and system administration.
  const groups: NavGroup[] = [
    {
      heading: tAdmin("navGroupOverview"),
      items: [{ href: "/manage", label: tAdmin("dashboard"), Icon: LayoutDashboard }],
    },
    {
      heading: t("catalog"),
      items: [
        { href: "/manage/catalog/products", label: tCatalog("navProducts"), Icon: Package },
        {
          href: "/manage/catalog/product-types",
          label: tCatalog("navProductTypes"),
          Icon: Shapes,
        },
        {
          href: "/manage/catalog/attributes",
          label: tCatalog("navAttributes"),
          Icon: SlidersHorizontal,
        },
        {
          href: "/manage/catalog/categories",
          label: tCatalog("navCategories"),
          Icon: FolderTree,
        },
        {
          href: "/manage/catalog/collections",
          label: tCatalog("navCollections"),
          Icon: Layers,
        },
      ],
    },
    {
      heading: tAdmin("navGroupSales"),
      items: [{ href: "/manage/orders/new", label: t("manualOrders"), Icon: Receipt }],
    },
    {
      heading: tAdmin("navGroupSystem"),
      items: [
        { href: "/manage/channels", label: t("channels"), Icon: Store },
        { href: "/manage/access", label: t("access"), Icon: Users },
        { href: "/manage/audit", label: t("audit"), Icon: ScrollText },
      ],
    },
  ];

  const allItems = groups.flatMap((group) => group.items);
  // The single deepest matching item is "the page you are on" -- it names the top
  // bar and is the only highlighted link (so nested pages don't light up two).
  const activeItem = allItems
    .filter((item) => isActive(pathname, item.href))
    .sort((a, b) => b.href.length - a.href.length)[0];
  // On a page nested below its section (e.g. a product detail under Products),
  // the top-bar section name turns into a back link to the section itself.
  const isNested =
    !!activeItem && !!pathname && pathname.startsWith(`${activeItem.href}/`);

  const renderBrand = (compact = false) => (
    <Link
      href="/manage"
      aria-label={tCommon("appName")}
      className="flex items-center gap-2 font-bold tracking-tight text-foreground"
    >
      <span
        aria-hidden
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-black text-primary-foreground"
      >
        پ
      </span>
      {compact ? null : (
        <span className="flex flex-col leading-tight">
          <span>{tCommon("appName")}</span>
          <span className="text-xs font-normal text-muted-foreground">{tAdmin("title")}</span>
        </span>
      )}
    </Link>
  );
  const brand = renderBrand(false);

  return (
    // The whole admin area is pinned to the viewport height so the page itself
    // never scrolls; the sidebar and the content area each scroll on their own.
    <div className="flex h-screen w-full overflow-hidden bg-background">
      {/* Sidebar (lg+): collapses to a slim icon rail via the header toggle. */}
      <aside
        className={cn(
          "no-scrollbar hidden shrink-0 flex-col gap-6 overflow-y-auto border-e border-border bg-card transition-[width] lg:flex",
          railed ? "w-16 p-2" : "w-64 p-4",
        )}
      >
        <div
          className={cn(
            "flex items-center pt-2",
            railed ? "flex-col gap-3" : "justify-between gap-2 px-2",
          )}
        >
          {renderBrand(railed)}
          <button
            type="button"
            onClick={() => setRailed((value) => !value)}
            aria-expanded={!railed}
            aria-label={railed ? tAdmin("expandMenu") : tAdmin("collapseMenu")}
            title={railed ? tAdmin("expandMenu") : tAdmin("collapseMenu")}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {railed ? (
              <PanelLeftOpen aria-hidden className="h-4 w-4" />
            ) : (
              <PanelLeftClose aria-hidden className="h-4 w-4" />
            )}
          </button>
        </div>

        {railed ? (
          // Icon-only rail: a flat list of every section, headings dropped.
          <nav aria-label={tAdmin("menuLabel")} className="flex flex-col items-center gap-1">
            {allItems.map((item) => (
              <SidebarLink
                key={item.href}
                item={item}
                active={item.href === activeItem?.href}
                compact
              />
            ))}
          </nav>
        ) : (
          <nav aria-label={tAdmin("menuLabel")} className="flex flex-col gap-5">
            {groups.map((group) => {
              const isCollapsed = collapsed[group.heading] ?? false;
              return (
                <div key={group.heading} className="flex flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.heading)}
                    aria-expanded={!isCollapsed}
                    className="flex items-center justify-between gap-2 rounded-md px-3 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <span>{group.heading}</span>
                    <ChevronDown
                      aria-hidden
                      className={cn(
                        "h-3.5 w-3.5 transition-transform",
                        isCollapsed && "-rotate-90",
                      )}
                    />
                  </button>
                  {isCollapsed
                    ? null
                    : group.items.map((item) => (
                        <SidebarLink
                          key={item.href}
                          item={item}
                          active={item.href === activeItem?.href}
                        />
                      ))}
                </div>
              );
            })}
          </nav>
        )}
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {/* Admin top bar */}
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-border bg-background/90 px-4 py-3 backdrop-blur">
          <div className="lg:hidden">{brand}</div>
          {/* Names the section you are actually on, not a global subtitle. On a
              nested page it becomes a back link to that section. */}
          <div className="hidden min-w-0 lg:block">
            {isNested && activeItem ? (
              <Link
                href={activeItem.href}
                className="inline-flex items-center gap-1.5 text-sm font-semibold text-foreground transition-colors hover:text-primary"
              >
                <ArrowRight aria-hidden className="h-4 w-4 shrink-0" />
                <span className="truncate">{activeItem.label}</span>
              </Link>
            ) : (
              <p className="truncate text-sm font-semibold text-foreground">
                {activeItem?.label ?? tAdmin("dashboard")}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              {tAdmin("backToStore")}
            </Link>
            <ThemeToggle />
            {user ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
              >
                {t("logout")}
              </Button>
            ) : null}
          </div>
        </header>

        {/* Mobile nav (horizontal scroller) -- same icons as the sidebar for parity. */}
        <nav
          aria-label={tAdmin("menuLabel")}
          className="flex gap-1 overflow-x-auto border-b border-border bg-card px-3 py-2 lg:hidden"
        >
          {allItems.map((item) => {
            const { Icon } = item;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={item.href === activeItem?.href ? "page" : undefined}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors",
                  item.href === activeItem?.href
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <Icon aria-hidden className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Scrolls for ordinary long pages; a page that wants a fixed frame with
            its own inner scroll region can fill this with `h-full`. */}
        <main className="no-scrollbar min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}

function SidebarLink({
  item,
  active,
  compact = false,
}: {
  item: NavItem;
  active: boolean;
  compact?: boolean;
}) {
  const { Icon } = item;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      aria-label={compact ? item.label : undefined}
      title={compact ? item.label : undefined}
      className={cn(
        "flex items-center rounded-md text-sm transition-colors",
        compact ? "h-10 w-10 justify-center" : "gap-3 px-3 py-2",
        active
          ? "bg-primary text-primary-foreground"
          : "text-foreground hover:bg-accent hover:text-accent-foreground",
      )}
    >
      <Icon aria-hidden className="h-4 w-4 shrink-0" />
      {compact ? null : item.label}
    </Link>
  );
}
