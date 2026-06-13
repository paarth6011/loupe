# Multi-tenancy — tenant data model & isolation

> Status: **shipped & live.** This is the tenant data model + Postgres
> row-level-security isolation that powers the hosted version
> ([getloupe.net](https://getloupe.net)). It's the foundation the rest of the
> multi-tenant product (signup, auth, billing) builds on; self-host deploys run
> single-tenant and are unaffected.

## Goal

Introduce **tenants** (accounts) and **users**, scope every domain row to a
tenant, and make cross-tenant data access **impossible at the database level** —
before any public signup exists. Phase 1 is "done" when:

- accounts and users exist,
- every domain row carries an `account_id`,
- a request runs as exactly one account, and
- a test proves one account **cannot** read another account's rows, even with a
  query that "forgets" to filter by account.

## Architecture this slots into

```
Frontend (Vercel)  ──https──▶  FastAPI backend (your VM)  ──▶  Postgres (your VM, RLS)
                                         │
                                         └──▶  Supabase (Auth only, free + keepalive cron)
```

- **Own Postgres** holds the hot, high-write data (no 500 MB cap, no pause).
- **Row-Level Security** is native Postgres — Supabase is *not* required for it.
- Auth provider (Supabase Auth vs. roll-our-own) is a **separate decision**; it
  only changes *how* `account_id` reaches the backend, not the model below.

## Data model

### New tables

- **`accounts`** — the tenant/org. `id` (int PK), `name`, `plan` (default
  `"free"`), `created_at`.
- **`users`** — `id` (int PK), `account_id` → `accounts` (FK, indexed), `email`
  (unique), `role` (`"owner"` | `"member"`, default `"owner"`), `created_at`.
  - `users.id` is the authenticated principal. Whether login is handled by
    Supabase Auth or our own code, the access token must carry the user's
    `account_id` so the backend can scope the request.

> **Why int PKs, not uuid:** every existing table uses int PKs. Consistency and
> simpler migrations win here; RLS compares ints fine, and account ids are never
> exposed as public slugs (RLS denies access regardless of guessability).

### Changes to existing tables

Add `account_id` (int FK → `accounts`, indexed, `NOT NULL` after backfill) to
**all five** domain tables — denormalized onto every one, including
`metric_samples`, so isolation is a single indexed filter with no joins:

| Table | Change |
|---|---|
| `workloads` | + `account_id`; **drop global-unique on `name`**, add unique `(account_id, name)` |
| `metric_samples` | + `account_id`; add composite index `(account_id, ts)` |
| `alerts` | + `account_id` |
| `monitors` | + `account_id` |
| `api_keys` | + `account_id` — **the ingestion boundary** (a key belongs to one account) |

`api_keys.account_id` is what makes ingestion automatic: `POST /metrics` with
`X-API-Key` resolves the key → its `account_id` → stamps that on the new sample
and on any auto-created workload.

## Isolation: two layers (defense-in-depth)

### Layer 1 — Postgres Row-Level Security (the real guard)

Enable RLS on the **four data tables** (`workloads`, `metric_samples`, `alerts`,
`monitors`). The identity/auth-bootstrap tables — `accounts`, `users`,
`api_keys` — are deliberately **not** under RLS: the API-key hash lookup and the
login-by-email lookup both run *before* a tenant is known (they are what
*establish* the tenant), so a "deny when no account set" policy would block the
very query that resolves the account. Those three are scoped with explicit
`account_id` filters in app code instead.

Each data table gets a policy of the form:

```sql
ALTER TABLE workloads ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON workloads
  USING (account_id = current_setting('app.current_account')::int);
```

Per request the backend sets `app.current_account` to the authenticated
account id. Even if app code forgets a `WHERE account_id = ?`, the database
returns zero rows from other tenants. This is why the change is tractable: the
existing `workload_id`-only queries become safe untouched.

**Two hard requirements for RLS to actually hold:**

1. **The app must connect as a non-superuser role.** Superusers (and table
   owners, unless `FORCE ROW LEVEL SECURITY`) bypass RLS. We add a restricted
   `loupe_app` role and use `FORCE ROW LEVEL SECURITY` on each table so even the
   owner is constrained.
2. **The tenant variable must be set for every statement in the request.** The
   ingest path commits mid-request and then runs more queries, so a
   per-transaction `SET LOCAL` would be cleared after that commit and the
   follow-up queries would see *no* account → deny everything. Therefore we use a
   **session-scoped** setting (`set_config('app.current_account', :id, false)`)
   established when the request checks out its connection, and **reset on
   connection return** to the pool (a SQLAlchemy `reset`/`checkin` event running
   `SELECT set_config('app.current_account', '', false)`), so a pooled connection
   can never leak one tenant's id into the next request.

### Layer 2 — application scoping (belt-and-suspenders)

A tenant-aware DB dependency yields a session already pinned to the current
account, and query helpers still filter by `account_id` explicitly. RLS is the
backstop; explicit filters keep intent obvious and protect the SQLite path
(below).

## Request → account plumbing

- **End-user requests (Supabase Auth):** the frontend signs the user in with
  Supabase and forwards Supabase's access token. The backend verifies it
  (`decode_supabase_token`, HS256 with the project JWT secret, `authenticated`
  audience), reads `sub` (the Supabase user UUID), and looks the user up by
  `users.supabase_user_id`. On first sight the account + user are
  **provisioned just-in-time** (no signup webhook to keep in sync). The resolved
  `account_id` scopes the request and sets `app.current_account`.
- **Admin requests (self-host):** the existing admin JWT still works and maps to
  the single `default` account, so the single-tenant deploy is unaffected.
- **Ingest requests (`X-API-Key`):** `verify_ingest_key` returns the `ApiKey`,
  whose `account_id` becomes the request's account. The current
  `require_ingest_auth` returns `None`; it will return the resolved account so
  the ingest handler can stamp `account_id` (and pin RLS).
- **SSE `/events`:** the stream ticket must carry `account_id` too, so live
  updates are tenant-scoped just like REST.

## Migration & backfill (`0010_multitenant`)

1. Create `accounts` and `users`.
2. Add **nullable** `account_id` to the five tables.
3. Insert one **default account** (`name="default"`); backfill all existing rows
   to it (preserves the current single-tenant deploy's data).
4. Set `account_id` **NOT NULL**.
5. Swap `workloads.name` unique → unique `(account_id, name)`; add
   `(account_id, ts)` index on `metric_samples`.
6. Create the `loupe_app` role, enable + **force** RLS, add policies.

> Steps 5–6 are Postgres-specific. On SQLite (the unit-test DB) RLS is a no-op,
> so the suite exercises **Layer 2** (app scoping); the **Layer 1** isolation
> proof runs against Postgres in CI (the `backend` job already has a Postgres
> service).

## Testing the guarantee

- **Postgres isolation test:** create accounts A and B, insert a workload under
  each, set `app.current_account` to A, and assert a *bare* `SELECT * FROM
  workloads` (no account filter) returns only A's row. Repeat for B. This proves
  RLS, not just app diligence.
- **App-scoping tests (SQLite):** the account-aware dependency filters correctly;
  ingest stamps the key's `account_id`; a second account's API key can't read the
  first's workloads.

## Deploy: enabling RLS enforcement (the `loupe_app` role)

RLS is **written by the migration but dormant until the app connects as a
non-superuser role** — superusers and `BYPASSRLS` roles skip row security
entirely. The single-host stack handles this with one opt-in secret:

- **Set `APP_DB_PASSWORD`** in `.env` (see `.env.prod.example`) and redeploy
  (`docker compose -f docker-compose.prod.yml up -d --build`).
- On boot, after `alembic upgrade head`, `start.sh` runs `python -m
  app.db_bootstrap`, which (idempotently) creates the `loupe_app` role
  (`LOGIN NOSUPERUSER NOBYPASSRLS`) and grants it DML on the app schema, with
  `ALTER DEFAULT PRIVILEGES` so future migrations' tables are covered too.
- **Migrations keep running as the owner** (`DATABASE_URL` / `POSTGRES_USER`);
  only request-serving switches to `loupe_app` (the backend derives that
  connection from `app_db_password` via `Settings.runtime_database_url()`).
- **Leave `APP_DB_PASSWORD` empty** for a single-tenant self-host instance: the
  app serves as the owner and RLS bypass is harmless with one tenant.

Verified end-to-end against Postgres 16: as the real `loupe_app` login, a bare
`SELECT` returns only the pinned account's rows, and an unset pin returns none.

> **Manual equivalent** (if provisioning by hand instead): as the owner, run
> `CREATE ROLE loupe_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '…';` then
> `GRANT USAGE ON SCHEMA public`, `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL
> TABLES IN SCHEMA public`, the matching `GRANT … ON ALL SEQUENCES`, and the two
> `ALTER DEFAULT PRIVILEGES … TO loupe_app` — then point the app's connection at
> `loupe_app`.

## Explicitly out of scope for Phase 1

Signup/login UI, the auth-provider choice, password reset, per-tenant
rate-limits/quotas, billing. Those are Phases 2–6.

## Auth provider: **Supabase Auth** (decided)

End-user login is handled by **Supabase Auth**; Loupe verifies the Supabase JWT
and maps it to a tenant. This keeps the dangerous parts (password hashing, reset
flows, email verification, rate-limiting) out of our codebase, and gives social
login / MFA as configuration later. Mechanics:

- Supabase signs user tokens **HS256 with the project JWT secret** — the same
  scheme `auth.py` already uses, so verification needs **no new dependency**
  (`decode_supabase_token`). Config: `SUPABASE_JWT_SECRET` (+ `authenticated`
  audience). Empty secret disables the path, so the self-host admin login is
  unaffected.
- `users.supabase_user_id` is the stable link (the token's `sub`). Users are
  **provisioned just-in-time** on first authenticated request — there is no
  signup webhook, so there is no two-systems-of-record drift to manage.
- **Keepalive:** Supabase free pauses a project after 7 days idle. Because Auth
  now sits on the login path, the keepalive cron (already planned for the DB) is
  load-bearing — it must ping the Supabase project, not just our Postgres.

> Not a one-way door: the data model is identical regardless of provider, so a
> later switch to self-issued tokens is a contained change (swap
> `decode_supabase_token` for `decode_token` in the dependency).
