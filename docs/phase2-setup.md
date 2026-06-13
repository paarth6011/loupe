# Phase 2 setup runbook — turning on Supabase end-user auth

> Operator checklist to go from "Phase 2 code merged" to "a stranger can sign up
> and log in." All the code is in place (see `docs/phase2-auth.md`); this is the
> wiring. Budget ~30 minutes. Nothing here touches the self-host single-admin
> login — that keeps working with all the values below left empty.

## Prerequisites

- Phase 1 (PR #34) and Phase 2 (PR #35) merged to `main`.
- RLS enforcement on (Phase 1 rollout): `APP_DB_PASSWORD` set in the VM `.env`
  and the stack redeployed. Multi-tenant signups **must** have this on. See
  `docs/multi-tenancy.md` → "enabling RLS enforcement".
- Access to: the Supabase dashboard, the VM (to edit `.env` + redeploy), the
  Vercel project (SaaS frontend), and the GitHub repo settings (secrets).

---

## Step 1 — Create the Supabase project

1. https://supabase.com → **New project**. Pick a name and a strong database
   password (you won't need the DB — Loupe uses its own Postgres — but Supabase
   requires one). Choose a region near your users.
2. Wait for provisioning to finish (~2 min).

## Step 2 — Two decisions

**a) Email confirmation.** Dashboard → **Authentication → Sign In / Providers →
Email**. Toggle **"Confirm email"**:
- **Off** → instant signup (recommended for a closed beta). The frontend signs
  the user straight in.
- **On** → users must click an emailed link first. The frontend already handles
  this: it shows "Check your email to confirm your account" and the dashboard
  appears once they confirm. Turn this on before a public launch.

**b) Token signing — JWKS (asymmetric) vs. legacy HS256.** The backend
(`decode_supabase_token`) supports **both**. Check **Project Settings → API →
JWT Keys**:
- **Current key is `ECC` / `RSA` (ES256/RS256)** — the modern Supabase default.
  Use the **JWKS path**: set `SUPABASE_URL` on the backend (Step 4a) and the
  backend fetches + caches the project's public keys automatically. ✅ This is
  what a freshly created project uses today.
- **Current key is `Legacy HS256 (Shared Secret)`** — use the **shared-secret
  path** instead: set `SUPABASE_JWT_SECRET` (the JWT secret) and leave
  `SUPABASE_URL` empty.

You set one or the other, not both — if `SUPABASE_URL` is set it takes the JWKS
path.

**c) Password-reset email — use a CODE, not a link.** The frontend resets
passwords with a **6-digit code** the user types in, because email scanners
(Gmail especially) pre-fetch magic links and burn the one-time token before the
user clicks (`otp_expired`). For the code to appear, edit the email template:
**Authentication → Emails → "Reset Password"** and make it surface the code and
**remove the link** (a clickable link can still be prefetched and would consume
the same token). Minimal body:

```html
<h2>Reset your password</h2>
<p>Enter this code in Loupe to set a new password:</p>
<p style="font-size:22px;font-weight:700;letter-spacing:3px">{{ .Token }}</p>
<p>This code expires in 1 hour. If you didn't request it, ignore this email.</p>
```

(Confirmation and magic-link emails can keep `{{ .ConfirmationURL }}`; only the
reset template needs to be code-only.)

## Step 3 — Grab the three values

From **Project Settings → API**:

| Value | Where it's used | Secret? |
|---|---|---|
| **Project URL** (`https://<ref>.supabase.co`) | backend (JWKS) + frontend + keepalive | public |
| **anon / public key** | frontend + keepalive | public (safe in bundle) |
| **JWT secret** | backend — only for the legacy HS256 path (Step 2b) | **secret — never commit** |

> On the JWKS path (the default), the backend needs only the **Project URL** —
> the signing keys it fetches are public, so there's no backend secret to manage.
> You only need the JWT secret if your project still signs with legacy HS256;
> keep it out of git (VM `.env`, or a CI secret store) if so.

## Step 4 — Wire the values in three places

### 4a. Backend (VM)

On the VM, edit `.env` (the gitignored one next to `docker-compose.prod.yml`).
**JWKS path (your project — ES256):** set the project URL; no secret needed.

```sh
SUPABASE_URL=https://<ref>.supabase.co
```

> Legacy HS256 path instead: leave `SUPABASE_URL` empty and set
> `SUPABASE_JWT_SECRET=<the JWT secret from Step 3>`.

Then redeploy:

```sh
docker compose -f docker-compose.prod.yml up -d --build backend
```

`docker-compose.prod.yml` forwards both `SUPABASE_URL` and `SUPABASE_JWT_SECRET`
to the backend (both empty = path disabled). Verify and sanity-check the JWKS
endpoint is reachable from the box:

```sh
docker compose -f docker-compose.prod.yml exec backend \
  sh -c 'test -n "$SUPABASE_URL" && echo "url set: $SUPABASE_URL" || echo "MISSING"'
curl -fsS "https://<ref>.supabase.co/auth/v1/.well-known/jwks.json" | head -c 200; echo
```

### 4b. Frontend (Vercel — the SaaS build)

Vercel project → **Settings → Environment Variables**, add for Production (and
Preview if you want it on previews):

```
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key from Step 3>
VITE_API_URL=https://YOUR-SUBDOMAIN.duckdns.org/api
```

These are **build-time** vars (Vite inlines them), so **trigger a redeploy** after
saving — existing builds won't pick them up. Their presence is what flips the
frontend into Supabase mode; without them the same bundle stays in admin mode.

> Self-host note: to instead run the *Docker* frontend in Supabase mode, set
> `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` in the VM `.env` and rebuild the
> `frontend` service. The normal self-host path leaves them empty (admin login).

### 4c. GitHub repo secrets (keepalive cron)

The `supabase-keepalive` workflow no-ops until these exist. From the repo root:

```sh
gh secret set SUPABASE_URL --body 'https://<ref>.supabase.co'
gh secret set SUPABASE_ANON_KEY --body '<anon key from Step 3>'
```

Then run it once to confirm it's green:

```sh
gh workflow run "Supabase keepalive"
gh run watch
```

Expect `HTTP 200` from the Auth health endpoint. After that it runs every 3 days
on its own — load-bearing, because the free tier pauses after ~7 days idle and
auth is on the login path.

## Step 5 — Smoke test (one real round-trip)

1. Open the Vercel URL in a fresh/incognito window → you should see **Email /
   Password** with a **"Need an account? Sign up"** link (not the admin
   username/password form). If you still see the admin form, the
   `VITE_SUPABASE_*` vars didn't make it into the build (re-check 4b + redeploy).
2. **Sign up** with a real address.
   - Confirmation off → you land on the dashboard immediately.
   - Confirmation on → you get the "check your email" notice; click the link, then
     sign in.
3. Confirm the dashboard is **empty/tenant-scoped** (a brand-new account, not the
   self-host data).
4. **Log out**, then **log back in**. Refresh mid-session — you should stay signed
   in (token auto-refresh).
5. (Isolation spot-check) Sign up a second account in another incognito window and
   confirm it can't see the first account's data.

## Step 6 — Ship it

- Flip **PR #35** from draft to **Ready for review** / merge once the smoke test
  passes (if you haven't already merged the stack).
- Tell early users the signup URL.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Login shows the admin username/password form | `VITE_SUPABASE_*` not in the build | Set both in Vercel, **redeploy** (build-time) |
| Sign-up works but every API call 401s | Backend `SUPABASE_URL` unset (JWKS path), wrong project, or the box can't reach the JWKS endpoint | Re-check 4a; `curl` the `.well-known/jwks.json` from the VM; confirm signing scheme (Step 2b) |
| 401s only after a while | Access token expired and didn't refresh | Confirm Supabase client has `autoRefreshToken` (it does) — check for clock skew / blocked Supabase domain |
| Keepalive workflow red | Wrong URL/key, or project paused | Re-set the two repo secrets; unpause the project in the dashboard |
| Users locked out after a quiet week | Project paused (keepalive not running) | Unpause; confirm the cron is enabled and green |

## Rollback (disable Supabase auth)

Fully reversible — clear the values and redeploy:

- VM `.env`: blank `SUPABASE_URL` (and `SUPABASE_JWT_SECRET` if used); Vercel:
  remove `VITE_SUPABASE_*` and redeploy. The app drops back to the single-admin
  login. (Provisioned `accounts`/`users` rows stay in the DB; they're harmless
  and reusable if you re-enable.)
