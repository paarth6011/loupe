import { apiFetch } from "./client";
import type { Monitor } from "../types";

export function listMonitors(workloadId: number): Promise<Monitor[]> {
  return apiFetch<Monitor[]>(`/workloads/${workloadId}/monitors`);
}

export function updateMonitor(
  workloadId: number,
  rule: string,
  body: { enabled?: boolean; threshold?: number | null },
): Promise<Monitor> {
  return apiFetch<Monitor>(`/workloads/${workloadId}/monitors/${rule}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
