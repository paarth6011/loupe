import { apiFetch } from "./client";
import type { Alert } from "../types";

export function listAlerts(params?: {
  workloadId?: number;
  resolved?: boolean;
}): Promise<Alert[]> {
  const query = new URLSearchParams();
  if (params?.workloadId != null)
    query.set("workload_id", String(params.workloadId));
  if (params?.resolved != null) query.set("resolved", String(params.resolved));
  const qs = query.toString();
  return apiFetch<Alert[]>(`/alerts${qs ? `?${qs}` : ""}`);
}
