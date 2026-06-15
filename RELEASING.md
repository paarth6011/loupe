# Releasing Loupe

This is the maintainer checklist for cutting a versioned release and publishing
container images. CI (lint + tests + build) must be green first.

## Cut a release

1. Update `CHANGELOG.md`: move items from **Unreleased** into a new dated version
   section.
2. Commit on `main`.
3. Tag and push:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which:

- builds the **backend** and **frontend** images and pushes them to GHCR as
  `ghcr.io/<owner>/loupe-backend` and `ghcr.io/<owner>/loupe-frontend`, tagged
  with the full version, `MAJOR.MINOR`, and `latest`;
- creates a GitHub Release with auto-generated notes.

The images are public/private according to your GHCR package settings; make them
public for an open-source release (Packages → package → Settings → Visibility).

## Publish the SDK to PyPI

The Python SDK ships separately from the app, under its own `sdk-v*` tags, so it
versions independently. Distribution name is **`loupe-llm`** (the plain `loupe`
was taken); the import name stays `loupe` (`pip install loupe-llm` →
`from loupe import track`).

**One-time PyPI setup (Trusted Publishing — no API token to store):**

1. Create a PyPI account at <https://pypi.org>.
2. Add a **pending** trusted publisher (the project doesn't exist on PyPI yet):
   PyPI → your account → **Publishing** → *Add a pending publisher* with:
   - PyPI Project Name: `loupe-llm`
   - Owner: `paarth6011` · Repository: `loupe`
   - Workflow name: `sdk-release.yml`
   - Environment: `pypi`
3. (Recommended) create a GitHub Environment named `pypi`
   (repo → Settings → Environments) — the workflow references it. It's
   auto-created on first run if you skip this, but an explicit one lets you add
   approval rules.

**Cut an SDK release:**

1. Bump `version` in `sdk/pyproject.toml` (PyPI versions are immutable — you can
   never re-upload the same one).
2. Commit on `main`, then tag and push:
   ```bash
   git tag sdk-v0.1.0
   git push origin sdk-v0.1.0
   ```

Pushing an `sdk-v*` tag triggers `.github/workflows/sdk-release.yml`, which builds
the sdist + wheel from `sdk/` and publishes to PyPI via OIDC. The first run
creates the project on PyPI (claiming the `loupe-llm` name).

## Run from published images

Once published, the stack can run without building locally:

```bash
docker run -p 8000:8000 \
  -e DATABASE_URL=... -e RUN_MIGRATIONS=1 \
  ghcr.io/<owner>/loupe-backend:latest
```

> **Frontend note:** the frontend bakes `VITE_API_URL` at build time (Vite
> inlines it). The published image defaults to `http://localhost:8000`, which is
> right for a local `docker run`. For a deployed frontend, rebuild with
> `--build-arg VITE_API_URL=https://your-backend-url`.

## Deploying behind a reverse proxy

The login brute-force throttle (`/auth/login`) keys on the client IP. With the
default local setup that's the real client — the frontend nginx serves only
static files, so browsers reach the backend directly.

If you put the backend **behind a reverse proxy or load balancer** (nginx,
Cloud Run, an ALB, etc.), every request appears to come from the proxy's IP
instead. The throttle then counts all clients against one shared counter — so a
single attacker can lock everyone out, and the per-IP limit is effectively
meaningless. Two env knobs — **already wired into `backend/start.sh` and
`docker-compose.prod.yml`, so you set env vars, not edit files** — make the
backend see the real client behind a trusted proxy:

- **`TRUSTED_PROXY_HOPS`** — the number of trusted proxies between the client and
  the app. The throttle then takes the `X-Forwarded-For` entry that many hops
  from the right (the address *your* proxy appended), which a client can't forge
  by prepending its own. The bundled single-host Caddy stack sets this to `1`
  (the compose default), so the throttle already sees the real client. Set it to
  your proxy count if you front the backend differently; `0` (the code default,
  used in plain local dev where the browser hits the backend directly) means
  "use the socket peer."
- **`FORWARDED_ALLOW_IPS`** — which immediate peers uvicorn trusts to honor
  `X-Forwarded-*` headers (defaults to `127.0.0.1`), so anything reading
  `request.client.host` also sees the forwarded IP. Set it to the proxy's
  address, or `"*"` **only** when a trusted proxy is the *only* way to reach the
  container (e.g. Cloud Run, where Google's front end fronts it).

Do **not** set `TRUSTED_PROXY_HOPS > 0` or widen `FORWARDED_ALLOW_IPS` without a
trusted proxy actually in front: it would let any client spoof `X-Forwarded-For`
and dodge the throttle.

> The internal Postgres user/db name is `cloudops` (a historical name); it's left
> as-is because renaming it would force wiping the database volume for zero
> user-visible benefit — it never appears outside the connection string.
