import { apiFetch } from "./client";
import type { ApiKey, ApiKeyCreated } from "../types";

export function listApiKeys(): Promise<ApiKey[]> {
  return apiFetch<ApiKey[]>("/apikeys");
}

export function createApiKey(name: string): Promise<ApiKeyCreated> {
  return apiFetch<ApiKeyCreated>("/apikeys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function revokeApiKey(id: number): Promise<void> {
  return apiFetch<void>(`/apikeys/${id}`, { method: "DELETE" });
}
