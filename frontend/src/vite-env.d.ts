/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend API base URL (defaults to http://localhost:8000). */
  readonly VITE_API_URL?: string;
  /** Supabase project URL — its presence (with the anon key) enables SaaS auth. */
  readonly VITE_SUPABASE_URL?: string;
  /** Supabase anon/public key (safe to ship in the client bundle). */
  readonly VITE_SUPABASE_ANON_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
