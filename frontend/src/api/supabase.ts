import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Dual-mode auth. The same frontend bundle ships to the hosted SaaS (Vercel) and
// to self-host (Docker). The presence of the Supabase env vars is the switch:
//
//   - both set      → "supabase" mode: end users sign up / sign in via Supabase
//                     Auth, and every API request carries a Supabase access token.
//   - either unset  → "admin" mode: the existing single-admin login
//                     (/auth/login + /auth/dev-login), unchanged — so self-host
//                     deployments keep working with no Supabase project.
//
// Vite inlines import.meta.env.* at build time, so this is decided per-build.
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isSupabaseMode = Boolean(url && anonKey);

// Non-null only in supabase mode. Keeping it nullable (rather than asserting)
// lets the admin-mode code paths import this module without tripping over a
// missing config — they simply never touch the client.
export const supabase: SupabaseClient | null = isSupabaseMode
  ? createClient(url!, anonKey!, {
      auth: {
        // Persist the session in localStorage and refresh the access token in
        // the background, so a reload keeps the user signed in and apiFetch can
        // read a fresh token synchronously-enough from getSession().
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;
