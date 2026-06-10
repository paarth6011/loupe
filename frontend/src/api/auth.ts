import { apiFetch, setToken } from "./client";
import type { TokenResponse } from "../types";

export async function login(username: string, password: string): Promise<void> {
  const data = await apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setToken(data.access_token);
}

/**
 * Attempt the frictionless dev login. The backend issues a token without
 * credentials only in non-production environments; in production it 404s and we
 * fall back to the normal sign-in form. Returns whether a token was obtained.
 */
export async function devLogin(): Promise<boolean> {
  try {
    const data = await apiFetch<TokenResponse>("/auth/dev-login", {
      method: "POST",
    });
    setToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}
