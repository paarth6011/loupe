import { apiFetch } from "./client";
import type { BaselineProfile, Workload } from "../types";

export function listWorkloads(): Promise<Workload[]> {
  return apiFetch<Workload[]>("/workloads");
}

export function getWorkloadBaselines(id: number): Promise<BaselineProfile[]> {
  return apiFetch<BaselineProfile[]>(`/workloads/${id}/baselines`);
}
