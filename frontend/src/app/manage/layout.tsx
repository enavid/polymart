import type { ReactNode } from "react";

import { AdminGuard } from "@/components/admin/admin-guard";
import { AdminShell } from "@/components/admin/admin-shell";

/**
 * Admin area layout: gate access to staff, then render the dedicated admin shell
 * (its own sidebar + top bar, full width) around every `/manage/*` page. The
 * shopper header/footer are intentionally absent here (see `AppShell`).
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <AdminGuard>
      <AdminShell>{children}</AdminShell>
    </AdminGuard>
  );
}
