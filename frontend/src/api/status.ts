import { apiFetch } from "./client";
import type { StatusPage, Workload } from "../types";

// Public status page. No auth is required; apiFetch simply omits the header
// when there's no token (a logged-out visitor), and the endpoint ignores it.
export function getStatus(): Promise<StatusPage> {
  return apiFetch<StatusPage>("/status");
}

// Publish or unpublish a workload on the status page (admin only).
export function setWorkloadPublic(
  workloadId: number,
  isPublic: boolean,
): Promise<Workload> {
  return apiFetch<Workload>(`/workloads/${workloadId}`, {
    method: "PATCH",
    body: JSON.stringify({ public: isPublic }),
  });
}
