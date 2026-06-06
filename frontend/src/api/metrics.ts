import { apiFetch } from "./client";
import type { MetricsSummary } from "../types";

export function getSummary(
  workloadId: number,
  window: string,
): Promise<MetricsSummary> {
  const params = new URLSearchParams({
    workload_id: String(workloadId),
    window,
  });
  return apiFetch<MetricsSummary>(`/metrics/summary?${params.toString()}`);
}
