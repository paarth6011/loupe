# AI-Powered Cloud Operations Dashboard

A full-stack dashboard for monitoring AI/cloud workloads: ingest latency / status /
token metrics, evaluate threshold alerts on the fly, and visualize health in a live
React dashboard. Everything runs locally via Docker Compose.

## Quickstart

```bash
cp .env.example .env        # optional — sensible defaults are baked in
docker compose up --build   # brings up db + backend + frontend + simulator
```

Then open **http://localhost:5173** and sign in with **admin / admin**.

The simulator immediately starts posting traffic for three workloads, so the charts
and alerts populate within seconds.

## Services & ports

| Service     | URL / port              | What it is                                 |
|-------------|-------------------------|--------------------------------------------|
| frontend    | http://localhost:5173   | React + TypeScript dashboard (nginx)       |
| backend     | http://localhost:8000   | FastAPI API (`/docs` for Swagger UI)       |
| db          | localhost:5432          | PostgreSQL 16                              |
| simulator   | —                       | Generates synthetic workload metrics       |

The backend runs `alembic upgrade head` on startup, so the schema is created
automatically on first boot.

## API surface

- `GET  /health`
- `POST /auth/login` → JWT
- `POST /metrics` (auth) — ingest a sample; evaluates thresholds on insert
- `GET  /workloads` (auth)
- `GET  /metrics/summary?workload_id=&window=` (auth) — p50/p95, error rate, count
- `GET  /alerts` (auth) — supports `?workload_id=` and `?resolved=` filters

## Tests

```bash
docker compose exec backend python -m pytest -q
```

## Configuration

All config is via environment variables (see `.env.example`): database URL, JWT
settings, the single admin user, and the alerting thresholds
(`LATENCY_THRESHOLD_MS`, `ERROR_RATE_THRESHOLD`, …).
