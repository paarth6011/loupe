# CLAUDE.md — AI-Powered Cloud Operations Dashboard

Project context for Claude Code. Read this before any task.

## What this is
A full-stack dashboard for monitoring AI/cloud workloads: collect metrics from
simulated workloads, detect failures and latency spikes, and visualize health.
This file describes the **MVP**. Later phases (Redis, Kubernetes/GKE, ML-based
detection, LLM incident summaries) are out of scope until the MVP works.

## North-star vision (NOT the MVP)
Production-grade observability + management platform with distributed workloads,
real-time pipelines, ML anomaly detection, and an LLM that generates
plain-English incident summaries. We build toward this in slices; not yet.

## MVP scope
- Monitor 2–3 simulated AI workloads.
- Ingest latency, status, and token-count metrics into Postgres.
- Aggregate metrics (latency p50/p95, error rate, request volume) over time windows.
- Threshold-based alerting evaluated on ingest.
- JWT auth (single user role).
- React + TypeScript dashboard: time-series charts + alerts panel.
- Everything runs locally via Docker Compose.

## Explicitly OUT of scope for the MVP (do not add unless asked)
- Kubernetes / GKE / Helm
- Redis or any caching/streaming layer
- ML or statistical anomaly detection (thresholds only)
- LLM-generated incident summaries
- Multi-tenant orgs, RBAC beyond a single user role
- Real distributed tracing

Keep it simple. Prefer the smallest thing that works and is testable.

## Tech stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, pydantic v2.
- DB: PostgreSQL 16.
- Frontend: React + TypeScript + Vite, Recharts for charts, fetch-based API client.
- Auth: JWT (python-jose), bcrypt password hashing (passlib).
- Local orchestration: Docker Compose (postgres + backend + frontend).
- Tests: pytest (backend); each feature lands with happy-path + one failure test.

## Data model
- `Workload`: id, name, created_at.
- `MetricSample`: id, workload_id (FK), ts, latency_ms, status ("ok"|"error"),
  tokens (nullable int).
- `Alert`: id, workload_id (FK), rule, message, triggered_at, resolved_at (nullable).

## API surface (MVP)
- `GET  /health`
- `POST /auth/login` -> JWT
- `POST /metrics` (auth) — ingest a MetricSample; evaluate thresholds on insert.
- `GET  /workloads` (auth)
- `GET  /metrics/summary?workload_id=&window=` (auth) — latency p50/p95,
  error rate, request count over the window.
- `GET  /alerts` (auth)

## Conventions
- Backend: type hints everywhere; pydantic schemas separate from ORM models;
  one router module per resource; config via env vars (pydantic-settings).
- Migrations via Alembic — never auto-create tables in prod paths.
- Frontend: typed API client in src/api; components dumb, pages own data fetching.
- Each backend feature lands with pytest coverage of the happy path + one failure.
- Conventional commits.

## Working agreement for Claude Code
- Tackle one numbered task at a time; confirm the stack runs before moving on.
- When a task is ambiguous, propose the smallest reasonable interpretation and proceed.
- Do not introduce out-of-scope tech to "future-proof." Add it in its phase.
