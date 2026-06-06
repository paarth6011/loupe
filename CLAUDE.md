# CLAUDE.md — AI-Powered Cloud Operations Dashboard

Project context for Claude Code. Read this before any task.

## Status
- **Phase 1 (MVP): COMPLETE.** Monitoring dashboard, metrics ingestion to
  Postgres, aggregations, threshold alerting, JWT auth, React+TS frontend,
  Docker Compose. Do not rebuild it.
- **Phase 2: IN PROGRESS (current focus).** LLM incident summaries + Redis caching.
- **Phase 3: NOT STARTED.** Kubernetes/GKE, ML detection, GCP deploy.

## What this is
A full-stack dashboard for monitoring AI/cloud workloads: collect metrics from
simulated workloads, detect failures and latency spikes, and visualize health.

## Phase 2 scope (BUILD THIS NOW)
- **LLM incident summaries:** when an Alert is created, generate a concise,
  plain-English summary of what happened from the alert + recent metric context,
  via the Anthropic API (Claude). Store it on the Alert and show it in the UI.
  A no-key template fallback keeps the stack runnable without an API key.
- **Redis caching:** cache the metrics-summary aggregation with a short TTL.
- **(Stretch) Real-time:** Redis pub/sub -> SSE so the dashboard updates live.
  Only after summaries + caching are solid.

### Phase 2 engineering rules
- The LLM call MUST be resilient: timeout + one retry; on failure the alert still
  fires and `Alert.summary` stays NULL (backfill later). Never block ingestion.
- The summarizer must be injectable/mockable behind an interface; unit-test
  summarization with a fake implementation (no real API calls in tests).
- Cost control: dedupe/group alerts by (workload_id, rule) within a time window
  so an alert storm does not trigger many LLM calls.
- Run summary generation as a FastAPI background task, not inline in the request.

## Explicitly OUT of scope until Phase 3
- Kubernetes / GKE / Helm
- GCP deployment (Cloud Run etc.)
- ML or statistical anomaly detection (thresholds only)
- Multi-tenant orgs / RBAC beyond a single user role
- Real distributed tracing
Keep it simple. Smallest thing that works and is testable.

## Tech stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, pydantic v2.
- DB: PostgreSQL 16. Cache: Redis 7 (Phase 2).
- LLM: Anthropic API / Claude (for incident summaries), with a no-key fallback.
- Frontend: React + TypeScript + Vite, Recharts, fetch-based API client.
  shadcn/ui for components.
- Auth: JWT (python-jose), bcrypt.
- Local orchestration: Docker Compose (postgres + redis + backend + frontend).
- Tests: pytest (backend); each feature lands with happy-path + one failure test.

## Data model
- `Workload`: id, name, created_at.
- `MetricSample`: id, workload_id (FK), ts, latency_ms, status ("ok"|"error"),
  tokens (nullable int).
- `Alert`: id, workload_id (FK), rule, message, severity, summary (nullable text,
  populated async by the LLM), triggered_at, resolved_at (nullable).

## API surface
- `GET  /health`
- `POST /auth/login` -> JWT
- `POST /metrics` (auth) — ingest a MetricSample; evaluate thresholds on insert.
- `GET  /workloads` (auth)
- `GET  /metrics/summary?workload_id=&window=` (auth) — latency p50/p95,
  error rate, request count. Cached in Redis (Phase 2).
- `GET  /alerts` (auth) — includes `summary` and `severity`.

## Conventions
- Type hints everywhere; pydantic schemas separate from ORM models;
  one router module per resource; config via env vars (pydantic-settings).
- Migrations via Alembic — never auto-create tables in prod paths.
- Frontend: typed API client in src/api; components dumb, pages own fetching.
- Conventional commits. Work on a `phase-2` branch.

## Working agreement for Claude Code
- Tackle one task at a time; confirm the stack runs before moving on.
- When a task is ambiguous, propose the smallest reasonable interpretation and proceed.
- Do not pull Phase 3 tech forward to "future-proof." Add it in its phase.
