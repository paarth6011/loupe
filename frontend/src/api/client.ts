import { isSupabaseMode, supabase } from "./supabase";

export const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "cloudops_token";

// --- Admin-mode token storage (self-host single-admin login) ---------------
// In supabase mode the access token lives inside the Supabase client's own
// persisted session, so these localStorage helpers are only used by the
// admin/self-host path (and the unit tests).

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * The access token to attach to API requests, resolved for the active auth mode.
 * Supabase mode reads the current session (the client keeps it fresh); admin
 * mode reads the localStorage token. Async because Supabase's getSession is.
 */
export async function getAccessToken(): Promise<string | null> {
  if (isSupabaseMode && supabase) {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }
  return getToken();
}

/** End the session for the active mode (used on logout and on a 401). */
export async function signOut(): Promise<void> {
  if (isSupabaseMode && supabase) {
    await supabase.auth.signOut();
    return;
  }
  clearToken();
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = await getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const resp = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (resp.status === 401) {
    // The session is no longer accepted — clear it so the app falls back to the
    // sign-in screen instead of looping on a dead token.
    await signOut();
    throw new ApiError(401, "Unauthorized");
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new ApiError(resp.status, text || resp.statusText);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
