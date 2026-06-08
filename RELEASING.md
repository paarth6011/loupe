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
