import { ApiError, apiFetch, setToken, signOut } from "./client";
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

// How hard to try the dev-login probe before falling back to the sign-in form.
// Total attempts = DEV_LOGIN_RETRIES + 1, with a linear backoff between them.
const DEV_LOGIN_RETRIES = 4;
const DEV_LOGIN_BACKOFF_MS = 300;

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Attempt the frictionless dev login. The backend issues a token without
 * credentials only in non-production environments; in production it 404s and we
 * fall back to the normal sign-in form. Returns whether a token was obtained.
 *
 * Right after `docker compose up` the backend may still be warming up, so the
 * first probe can hit connection-refused or a 5xx from a half-ready server. We
 * retry those transient failures with a short backoff so a cold start doesn't
 * briefly bounce the developer to the sign-in screen. A real 404 is the
 * production signal ("this endpoint does not exist here") — never retried; we
 * fall straight back to the login form.
 */
export async function devLogin(): Promise<boolean> {
  for (let attempt = 0; attempt <= DEV_LOGIN_RETRIES; attempt++) {
    try {
      const data = await apiFetch<TokenResponse>("/auth/dev-login", {
        method: "POST",
      });
      setToken(data.access_token);
      return true;
    } catch (err) {
      // 404 means we're not on a dev box (production) — stop immediately.
      if (err instanceof ApiError && err.status === 404) return false;
      // Otherwise it's transient (backend still booting); back off and retry.
      if (attempt < DEV_LOGIN_RETRIES) {
        await sleep(DEV_LOGIN_BACKOFF_MS * (attempt + 1));
      }
    }
  }
  return false;
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

// Verifying a recovery code establishes a real (recovery) session, which makes
// Supabase fire SIGNED_IN. During the login-initiated reset flow that event must
// NOT bounce the user to the dashboard — they still have to set a new password.
// ForgotPassword raises this flag for the duration of the flow; App's auth
// listener ignores auth events while it's set. (The link-based recovery path in
// App is unaffected — it never sets this.)
let _recoveryInProgress = false;
export function setRecoveryInProgress(v: boolean): void {
  _recoveryInProgress = v;
}
export function isRecoveryInProgress(): boolean {
  return _recoveryInProgress;
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
