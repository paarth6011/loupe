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

**b) Token signing — HS256 (shared secret) vs. JWKS.** The backend
(`decode_supabase_token`) currently verifies the **legacy shared HS256 secret**.
Check **Project Settings → API → JWT Keys** (or "JWT Settings"):
- If the active key is the **shared/HS256 secret** → you're done, no code needed.
- If the project uses **asymmetric signing keys (ECC/RSA, i.e. RS256/ES256)** →
  our HS256 verify will reject the tokens. Two options: keep/use the **legacy
  JWT secret** if the project still offers it, or ask for the **JWKS follow-up**
  (a contained change in `auth.py` only — fetch + cache the project's JWKS and
  verify RS/ES256). Decide before going live.

## Step 3 — Grab the three values

From **Project Settings → API**:

| Value | Where it's used | Secret? |
|---|---|---|
| **Project URL** (`https://<ref>.supabase.co`) | frontend + keepalive | public |
| **anon / public key** | frontend + keepalive | public (safe in bundle) |
| **JWT secret** | backend (token verification) | **secret — never commit** |

> Keep the JWT secret out of git. It goes only in the VM `.env` (gitignored) and,
> if you later use CI to deploy, in a CI secret store.

## Step 4 — Wire the values in three places

### 4a. Backend (VM)

On the VM, edit `.env` (the gitignored one next to `docker-compose.prod.yml`):

```sh
SUPABASE_JWT_SECRET=<the JWT secret from Step 3>
```

Then redeploy:

```sh
docker compose -f docker-compose.prod.yml up -d --build backend
```

`docker-compose.prod.yml` already forwards `SUPABASE_JWT_SECRET` to the backend
(empty = path disabled). Verify it's set inside the container:

```sh
docker compose -f docker-compose.prod.yml exec backend \
  sh -c 'test -n "$SUPABASE_JWT_SECRET" && echo "secret set" || echo "MISSING"'
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
| Sign-up works but every API call 401s | Backend `SUPABASE_JWT_SECRET` unset/wrong, or project uses JWKS not HS256 | Re-check 4a; verify HS256 vs JWKS (Step 2b) |
| 401s only after a while | Access token expired and didn't refresh | Confirm Supabase client has `autoRefreshToken` (it does) — check for clock skew / blocked Supabase domain |
| Keepalive workflow red | Wrong URL/key, or project paused | Re-set the two repo secrets; unpause the project in the dashboard |
| Users locked out after a quiet week | Project paused (keepalive not running) | Unpause; confirm the cron is enabled and green |

## Rollback (disable Supabase auth)

Fully reversible — clear the values and redeploy:

- VM `.env`: blank `SUPABASE_JWT_SECRET`; Vercel: remove `VITE_SUPABASE_*` and
  redeploy. The app drops back to the single-admin login. (Provisioned
  `accounts`/`users` rows stay in the DB; they're harmless and reusable if you
  re-enable.)
