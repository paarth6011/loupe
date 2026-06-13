# Phase 2 — Real auth (Supabase end-user sign-in)

> Status: **in progress.** Phase 1 (tenancy + RLS isolation) is code-complete;
> the backend already verifies a Supabase JWT and provisions the account/user
> just-in-time (`app/deps.py`, `app/auth.py:decode_supabase_token`). Phase 2
> makes real people sign up and log in — almost all of the remaining work is on
> the **frontend** and in **ops**, not the data layer.

## Progress (this branch)

The **build-now** slice (everything that doesn't need a live Supabase project)
has landed:

- **Frontend dual-mode** (`src/api/supabase.ts`): the presence of
  `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` switches between Supabase mode
  (SaaS) and the existing single-admin mode (self-host) — one bundle, no fork.
- **Token plumbing** (`src/api/client.ts`): `apiFetch` now sources the bearer
  token from the active mode (Supabase session or the admin localStorage token)
  and signs out of the right one on a 401.
- **Auth UI** (`src/pages/LoginPage.tsx`, `src/App.tsx`): email/password
  sign-up, sign-in, and password-reset against Supabase; route gating on the
  Supabase session (`getSession` + `onAuthStateChange`). Self-host login is
  untouched. Covered by `LoginPage.test.tsx`.
- **Backend tests** (`tests/test_supabase_auth.py`): verify a test-signed token
  resolves and JIT-provisions a tenant (and reuses it for the same `sub`);
  wrong-secret / expired / no-secret tokens are rejected.
- **Keepalive cron** (`.github/workflows/supabase-keepalive.yml`): scheduled
  ping of the Supabase Auth health endpoint; no-ops until the secrets are set.
- **Config**: `frontend/.env.example` + optional `VITE_SUPABASE_*` build args in
  `frontend/Dockerfile` (empty by default → self-host stays in admin mode).

**Remaining (needs your action / a Supabase project):**

1. Create the Supabase project; set `SUPABASE_JWT_SECRET` on the backend and
   `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` on the frontend build (Vercel)
   and the `SUPABASE_URL` / `SUPABASE_ANON_KEY` repo secrets (keepalive).
2. Decide **email confirmation** on/off, and **shared HS256 secret vs. JWKS**
   (see "Decisions needed" below). The current `decode_supabase_token` uses the
   shared HS256 secret; JWKS would be a follow-up in `auth.py` only.
3. One manual end-to-end sign-up → dashboard → logout round-trip before launch.

## Goal / definition of done

A stranger can visit the Vercel-hosted app, **sign up with email + password**,
land on a dashboard scoped to their own (auto-provisioned) tenant, log out, and
log back in — with their session surviving a refresh and the access token
auto-refreshing. Phase 2 is done when:

- the frontend authenticates against **Supabase Auth** (not `/auth/login`),
- every API request carries the Supabase access token,
- sign-up, log-in, log-out, and "session expired → re-auth" all work,
- the **single-admin self-host login still works** (unchanged), and
- the Supabase project can't silently pause and lock everyone out (keepalive).

Polish — naming your org, inviting teammates, first-run empty states — is
**Phase 3 (onboarding UX)**, deliberately out of scope here.

## What Phase 1 already provides

- `decode_supabase_token` verifies a Supabase JWT (HS256, `authenticated`
  audience) using `SUPABASE_JWT_SECRET`.
- `get_current_user` resolves that token → JIT-provisions `accounts` + `users`
  (keyed on `users.supabase_user_id`) → pins the request to the tenant.
- `require_ingest_auth` and the SSE stream already accept it too.

So the backend is **ready**; it just needs `SUPABASE_JWT_SECRET` set and a real
token arriving from the browser.

## Architecture

```
Browser ──(@supabase/supabase-js: sign-up / sign-in)──▶ Supabase Auth
   │  holds the session, auto-refreshes the access token
   ▼
apiFetch attaches `Authorization: Bearer <supabase access token>`
   ▼
FastAPI (verifies JWT, JIT-provisions tenant, pins RLS)  ──▶ Postgres
```

## Work items

### 1. Supabase project setup (your action)

- Create the project; copy **Project URL** + **anon key** (public, for the
  frontend) and the **JWT Secret** (secret, for the backend).
- Decide **email confirmation**: on (users must click a link) or off (instant
  signup, simplest for a closed beta). Recommendation: **off for beta**, on
  before public launch.

### 2. Backend — token verification (one decision)

`SUPABASE_JWT_SECRET` already wires the **legacy shared HS256 secret** path,
which still exists on every project and is the shortest route to working auth.
**Decision:** newer Supabase projects default to **asymmetric signing keys**
(ES256/RS256 via a JWKS endpoint) and are phasing the shared secret out. Options:

- **Start on the shared HS256 secret** (matches `decode_supabase_token` as
  written; zero new code) — recommended to get auth working, *or*
- **Implement JWKS verification** now (fetch + cache the project's JWKS, verify
  RS/ES256) — more future-proof, ~a half-day of work in `auth.py`.

Recommendation: ship on the shared secret, add JWKS as a fast-follow if/when the
project switches to signing keys. (Either way the rest of the stack is identical
— only the verify step changes.)

### 3. Frontend — Supabase integration (the bulk of Phase 2)

- Add **`@supabase/supabase-js`**; create a client from
  `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` (baked at build, like
  `VITE_API_URL`).
- **Replace token storage** in `src/api/client.ts`: today `getToken()` reads a
  string from `localStorage`. Switch it to read the **current Supabase session's
  access token** (the client persists + refreshes it). `apiFetch` keeps
  attaching `Authorization: Bearer …` unchanged; on 401 it should trigger
  Supabase `signOut()` instead of just clearing a key.
- **`src/pages/LoginPage.tsx`**: add **sign-up** and **sign-in** (email +
  password) calling `supabase.auth.signUp` / `signInWithPassword`; surface
  Supabase errors; add a **log-out** action and a **password-reset** link
  (Supabase emails it).
- **Route gating** (`App.tsx`): gate on the Supabase session (`getSession` +
  `onAuthStateChange`) rather than presence of a localStorage token.
- **`src/api/auth.ts`**: the stream ticket flow (`POST /auth/stream-ticket`)
  stays — it just runs with the Supabase token now (backend already accepts it).

### 4. Dual-mode: SaaS vs. self-host (keep both working)

The same frontend ships to Vercel (SaaS) and to self-host (Docker). Gate on the
Supabase env:

- **`VITE_SUPABASE_URL` present →** Supabase mode (sign-up/sign-in via Supabase).
- **absent →** today's **single-admin mode** (`/auth/login` + `/auth/dev-login`),
  unchanged — so the self-host instance and `DEPLOY-gcp.md` keep working.

This keeps one codebase and avoids a fork.

### 5. Keepalive cron (load-bearing)

Supabase free **pauses a project after 7 days idle**, and Auth now sits on the
login path — a paused project means *nobody can log in*. A scheduled ping
(e.g. a GitHub Actions cron hitting a trivial Supabase REST/auth endpoint every
few days) keeps it warm. This must target **Supabase**, not just our Postgres.

## Decisions needed before coding

1. **Email confirmation on or off for beta?** (Recommend off.)
2. **Shared HS256 secret vs. JWKS verification?** (Recommend shared secret now.)
3. **Keepalive home:** GitHub Actions cron vs. the VM's cron. (Recommend GH
   Actions — no extra moving parts on the box.)

## Testing

- **Backend:** a unit test that a token signed with a test `SUPABASE_JWT_SECRET`
  resolves to a JIT-provisioned account (and a second user under the same
  `sub` reuses it); a malformed/expired token → 401. These run on SQLite and
  need no Supabase.
- **Frontend:** component tests for the login/sign-up form states (loading,
  error, success) with the Supabase client mocked; the existing `client.test.ts`
  pattern covers `apiFetch` token attach + 401 handling.
- **Manual:** one real sign-up → dashboard → logout → login round-trip against
  the actual Supabase project before launch.

## Out of scope (→ later phases)

Org/account naming and team invites, first-run empty states and a setup wizard
(**Phase 3**); per-tenant rate limits and quotas (**Phase 4**); billing
(**Phase 6**). Social login / MFA are config toggles in Supabase we can enable
whenever, not Phase 2 work.
