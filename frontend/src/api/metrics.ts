import { apiFetch } from "./client";
import type { MetricsSummary, MetricsTimeseries } from "../types";

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

export function getTimeseries(
  workloadId: number,
  window: string,
  bucket: string,
): Promise<MetricsTimeseries> {
  const params = new URLSearchParams({
    workload_id: String(workloadId),
    window,
    bucket,
  });
  return apiFetch<MetricsTimeseries>(
    `/metrics/timeseries?${params.toString()}`,
  );
}
