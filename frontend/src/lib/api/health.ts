import { apiGet } from "@/lib/api/client";

export type HealthState = "healthy" | "degraded" | "unhealthy";

export interface ComponentHealth {
  name: string;
  state: HealthState;
  detail: string;
}

export interface HealthReport {
  state: HealthState;
  components: ComponentHealth[];
}

export function fetchHealth(): Promise<HealthReport> {
  return apiGet<HealthReport>("/health/");
}
