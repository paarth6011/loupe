import { apiFetch, setToken } from "./client";
import type { TokenResponse } from "../types";

export async function login(username: string, password: string): Promise<void> {
  const data = await apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setToken(data.access_token);
}
