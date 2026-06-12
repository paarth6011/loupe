# Security Policy

## Security model

Loupe is **self-hosted**: you run it, and you own the deployment and its network
exposure. It is built for a single-admin, localhost-first workflow, with an
explicit path to a hardened production deployment (see the checklist below). The
defaults are tuned for zero-friction local development and are **not** safe to
expose to a network as-is — the backend enforces that boundary at boot.

## What's already in place

- **Boot guard.** With `ENVIRONMENT=production`, the backend **refuses to start**
  if `JWT_SECRET` or `ADMIN_PASSWORD` is still an insecure default.
- **Authentication.** JWT-based admin auth, plus a brute-force throttle on
  `/auth/login` (per-client, with lockout after repeated failures).
- **Ingestion keys.** Per-source API keys for `POST /metrics`, stored only as
  SHA-256 hashes and revocable from the dashboard — the plaintext is shown once.
- **Live stream.** The SSE endpoint authenticates with a short-lived, read-only
  *stream ticket*, not the admin token, so the full admin JWT never travels in a
  URL (where it would otherwise leak into proxy logs and browser history).
- **Local convenience, production safety.** Frictionless dev auto-login is
  disabled in production; there it returns 404 and a real login is required.

## Supported versions

Loupe is pre-1.0. Only the latest tagged release receives security fixes; there
are no long-term-support branches yet.

| Version        | Supported |
| -------------- | --------- |
| 0.1.x (latest) | ✅        |
| < 0.1.0        | ❌        |

## ⚠️ Before exposing this to a network

The development defaults are not safe for public deployment. Change these before
putting Loupe on any reachable network:

- **Default credentials.** The admin login defaults to `admin` / `admin`. Set a
  strong `ADMIN_PASSWORD` (and ideally a non-default `ADMIN_USERNAME`).
- **JWT secret.** `JWT_SECRET` defaults to `change-me-in-prod`. Set a long random
  value; anyone who knows it can forge admin sessions.
- **Secrets in env.** Don't commit real secrets. In a real deployment use a
  secret manager (the GCP Terraform in `infra/terraform/` uses Secret Manager).
- **TLS.** Terminate HTTPS in front of the services (load balancer / reverse
  proxy). The app does not do TLS itself.
- **Reverse proxy & client IPs.** The login throttle keys on the client IP. If
  you run behind a proxy or load balancer, start uvicorn with `--proxy-headers`
  and a trusted `--forwarded-allow-ips` so it sees the real client IP — otherwise
  every request appears to come from the proxy and the throttle is ineffective.
  See [RELEASING.md](RELEASING.md) for details.
- **Rotate ingestion keys.** Revoke keys you no longer use from the dashboard,
  and never commit them.
- **Terraform state holds secrets.** The state stores the generated JWT signing
  key and DB password, plus the admin password, in plaintext. Anyone who can
  read it can forge admin tokens. Use an encrypted, access-controlled remote
  backend (see the commented example in `infra/terraform/versions.tf`); state
  files are already git-ignored.

> **Enforced (secure by default):** `ENVIRONMENT` defaults to `production`, so the
> backend refuses to start while `JWT_SECRET` or `ADMIN_PASSWORD` is an insecure
> default — a deployment that forgets to configure it fails closed. You must opt
> into the permissive local-dev behavior explicitly with `ENVIRONMENT=dev`, which
> allows the insecure defaults (and logs a warning). The Compose stack and the
> test suite set `ENVIRONMENT=dev` for you.

## Known limitations (accepted risks)

These are conscious trade-offs for the current single-admin MVP, not oversights:

- **Session tokens are stateless and browser-stored.** The admin JWT is held in
  `localStorage` and carried in the `Authorization` header (so there is no CSRF
  surface). It is a stateless token with a fixed TTL
  (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 60) and **no server-side revocation** —
  "log out" only clears the browser copy, and rotating the password does not
  invalidate already-issued tokens. Consequences to be aware of: a leaked token
  is valid until it expires, and any future XSS in the dashboard would be enough
  to exfiltrate it and take over the session. Keep the TTL short, and treat XSS
  in the frontend as high severity. A token denylist / `jti` is future work.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately via GitHub Security Advisories — the **"Report a vulnerability"**
button on the repository's **Security** tab.

We aim to **acknowledge a report within 3 business days** and will agree on a
remediation timeline from there. We ask for **coordinated disclosure**: please
give us a reasonable window to ship a fix before any public write-up. Reporters
who want credit will be credited in the advisory and release notes. There is no
paid bug-bounty program.

### In scope

Authentication or authorization bypass, privilege escalation, injection (SQL,
command, etc.), anything that defeats a production safeguard (e.g. the boot guard
or the stream-ticket scoping), and exposure of secrets or credentials.

### Not a vulnerability

- The **development defaults** (`admin` / `admin`, `change-me-in-prod`). These
  are intentional, documented, and blocked in production by the boot guard.
- Findings that require an already-compromised host, or a valid admin token /
  ingestion key.
- Volumetric denial-of-service (resource exhaustion by traffic volume).
