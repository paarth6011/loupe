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
> `--build-arg VITE_API_URL=https://your-backend-url` (see `DEPLOYMENT.md`).

## Deploying behind a reverse proxy

The login brute-force throttle (`/auth/login`) keys on the client IP via
`request.client.host`. With the default setup that's correct — the frontend
nginx serves only static files, so browsers reach the backend directly and the
IP is the real client.

If you put the backend **behind a reverse proxy or load balancer** (nginx,
Cloud Run, an ALB, etc.), every request appears to come from the proxy's IP
instead. The throttle then counts all clients against one shared counter — so a
single attacker can lock everyone out, and the per-IP limit is effectively
meaningless. When (and only when) a trusted proxy sits in front, start uvicorn
so it honors the forwarded client IP:

```sh
# backend/start.sh — add the proxy flags
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" \
     --proxy-headers --forwarded-allow-ips="*"
```

Do **not** enable `--forwarded-allow-ips` without a proxy in front: it would let
any client spoof `X-Forwarded-For` and dodge the throttle. Narrow it to the
proxy's address range in production rather than `"*"` where you can.

## One-time: finish the rename to `loupe`

The code, dashboard, SDK, compose project, and image names are already `loupe`.
Two things live outside the repo and are done by hand when you're ready:

1. **GitHub repo:** Settings → rename `cloud-ops-dashboard` → `loupe`. GitHub
   keeps redirects from the old name, so existing clones/links keep working.
2. **Local folder** (optional, cosmetic):
   ```bash
   cd ..
   mv cloud-ops-dashboard loupe
   ```
   Nothing references the folder name — the compose `name: loupe` fixes the
   container prefix regardless.

Left intentionally unchanged: the internal Postgres user/db name `cloudops`.
Renaming it would force wiping the database volume for zero user-visible benefit;
it never appears outside the connection string.
