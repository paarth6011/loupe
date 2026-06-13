import { apiFetch, setToken, signOut } from "./client";
import { supabase } from "./supabase";
import type { TokenResponse } from "../types";

// --- Admin mode (self-host single-admin login) -----------------------------

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

// --- Supabase mode (hosted SaaS end-user auth) -----------------------------
// These talk to Supabase Auth directly; the backend never sees the password.
// On success the Supabase client persists the session, and apiFetch picks up
// the access token from there (see getAccessToken in client.ts). The first
// authenticated API request JIT-provisions the account/user on the backend.

function requireSupabase() {
  if (!supabase) {
    throw new Error("Supabase auth is not configured in this build.");
  }
  return supabase;
}

/** Sign in an existing user with email + password. Throws on bad credentials. */
export async function signInWithPassword(
  email: string,
  password: string,
): Promise<void> {
  const { error } = await requireSupabase().auth.signInWithPassword({
    email,
    password,
  });
  if (error) throw error;
}

/**
 * Register a new user. With email confirmation enabled the returned session is
 * null until the user clicks the emailed link; with it disabled they are signed
 * in immediately. `needsConfirmation` tells the caller which message to show.
 */
export async function signUpWithPassword(
  email: string,
  password: string,
): Promise<{ needsConfirmation: boolean }> {
  const { data, error } = await requireSupabase().auth.signUp({
    email,
    password,
  });
  if (error) throw error;
  return { needsConfirmation: data.session === null };
}

/**
 * Send a password-reset email. We use a 6-digit CODE rather than a magic link:
 * email scanners (Gmail in particular) pre-fetch links and burn the one-time
 * token before the user clicks, causing "otp_expired". A typed code has no URL
 * to prefetch. (For this to work, the Supabase "Reset Password" email template
 * must surface `{{ .Token }}` and omit the link.) `redirectTo` is still passed
 * for the legacy link path, harmless when the template is code-only.
 */
export async function sendPasswordReset(email: string): Promise<void> {
  const { error } = await requireSupabase().auth.resetPasswordForEmail(email, {
    redirectTo: window.location.origin,
  });
  if (error) throw error;
}

/**
 * Exchange the emailed recovery code for a session, so the subsequent
 * updatePassword() call is authorized. Throws on a wrong/expired code.
 */
export async function verifyRecoveryCode(
  email: string,
  token: string,
): Promise<void> {
  const { error } = await requireSupabase().auth.verifyOtp({
    email,
    token,
    type: "recovery",
  });
  if (error) throw error;
}

/** Set a new password for the current (recovery) session. */
export async function updatePassword(password: string): Promise<void> {
  const { error } = await requireSupabase().auth.updateUser({ password });
  if (error) throw error;
}

/** Mode-agnostic logout (Supabase signOut, or clears the admin token). */
export async function logout(): Promise<void> {
  await signOut();
}
