import { AdminDashboard } from "@/components/admin/admin-dashboard";

/** Admin landing: an overview dashboard (KPIs + quick links). Access to
 *  `/admin/*` is gated to staff by the admin layout. */
export default function AdminIndexPage() {
  return <AdminDashboard />;
}
