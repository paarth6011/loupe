import { apiFetch } from "./client";
import type { Workload } from "../types";

export function listWorkloads(): Promise<Workload[]> {
  return apiFetch<Workload[]>("/workloads");
}
