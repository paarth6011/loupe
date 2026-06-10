# CLAUDE.md — AI-Powered Cloud Operations Dashboard

Project context for Claude Code. Read this before any task.

## Status
- **Phase 1 (MVP): COMPLETE.** Dashboard, metrics ingestion, aggregations,
  threshold alerting, JWT auth, React+TS frontend, Docker Compose.
- **Phase 2: COMPLETE.** LLM incident summaries + Redis caching.
- **Phase 3: IN PROGRESS (current focus).** Deploy to GCP, real distributed
  workloads, smarter (statistical) detection, distributed tracing.

## What this is
A full-stack platform for monitoring AI/cloud workloads: collect metrics from
distributed workloads, detect failures/latency spikes, summarize incidents with
an LLM, and visualize health — now deployed and running on GCP.

## Phase 3 scope — DO IN ORDER, do not skip ahead

### 3a. Deploy to Cloud Run (DO THIS FIRST)
- Production Dockerfiles for backend and frontend (multi-stage, non-root).
- Push images to Artifact Registry.
- Deploy backend + frontend to Cloud Run.
- Cloud SQL (Postgres) instead of the local Postgres container.
- Memorystore (Redis) instead of the local Redis container.
- All secrets via Secret Manager — never in images, never committed.
- Add a `/ready` readiness endpoint (checks DB + Redis) alongside `/health`.
- Get it working with `gcloud`/console first, THEN codify the GCP resources in
  Terraform and commit it.

### 3b. GKE / Kubernetes (ONLY after 3a is live and stable)
- K8s manifests (Deployment, Service, Ingress, HPA) or a small Helm chart.
- Liveness probe -> `/health`, readiness probe -> `/ready`.
- Horizontal Pod Autoscaler on the backend.
- Deploy to a GKE Autopilot cluster.
- This is the distributed-systems showcase; do not start it until the app
  genuinely runs on Cloud Run.

### 3c. Smarter detection + distributed workloads + tracing
- Statistical anomaly detection: rolling-window z-score and/or EWMA baseline per
  (workload, metric). MUST be explainable — record which detector fired on the
  Alert. No black-box ML models.
- Real distributed workloads: deploy the simulated workloads as separate services
  /jobs that push metrics over the network (not local scripts).
- Distributed tracing: OpenTelemetry across services, export to Cloud Trace.
  Attach trace_id to metric samples so alerts can link to traces.

### Phase 3 engineering rules
- Cloud Run before Kubernetes. Always.
- Secrets only via Secret Manager. Never bake credentials into images or commit them.
- Health (`/health`, liveness) and readiness (`/ready`, checks deps) endpoints are
  required before any GKE work.
- Detection must be explainable; prefer statistical methods you can defend over
  opaque models.
- Infra-as-code: prototype with gcloud, then codify in Terraform and commit it.
- Keep the local Docker Compose stack working as the dev environment.

## Explicitly OUT of scope (future, not now)
- Multi-region / HA failover
- Pager integrations (PagerDuty/Opsgenie), SLO burn-rate alerting
- Multi-cloud
- Fine-grained autoscaling/cost tuning beyond a basic HPA
Keep it simple. Smallest thing that works, is testable, and is explainable.

## Tech stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, pydantic v2.
- Detection: numpy/scipy (or statsmodels) for z-score / EWMA baselines.
- DB: PostgreSQL 16 (local) / Cloud SQL (deployed).
- Cache: Redis 7 (local) / Memorystore (deployed).
- LLM: pluggable incident summarizer — Anthropic Claude API, a local Ollama
  server, or a deterministic $0 template fallback (configurable; defaults to
  Claude when an API key is set, else the template).
- Frontend: React + TypeScript + Vite, Recharts, shadcn/ui.
- Auth: JWT (python-jose), bcrypt.
- Cloud: GCP — Cloud Run, Artifact Registry, Cloud SQL, Memorystore,
  Secret Manager, GKE Autopilot (3b), Cloud Trace (3c).
- IaC: Terraform. CI/CD: GitHub Actions (build, test, deploy).
- Observability: OpenTelemetry -> Cloud Trace.
- Local orchestration: Docker Compose (dev). Tests: pytest.

## Data model
- `Workload`: id, name, region (nullable), endpoint (nullable), created_at.
- `MetricSample`: id, workload_id (FK), ts, latency_ms, status ("ok"|"error"),
  tokens (nullable int), trace_id (nullable).
- `Alert`: id, workload_id (FK), rule, message, severity, summary (nullable text),
  detector ("threshold"|"zscore"|"ewma"), triggered_at, resolved_at (nullable).
- `Baseline` (for detection): id, workload_id (FK), metric, mean, stddev, window,
  updated_at.

## API surface
- `GET  /health`  — liveness.
- `GET  /ready`   — readiness; checks DB + Redis.
- `POST /auth/login` -> JWT
- `POST /metrics` (auth) — ingest a sample; run detection on insert.
- `GET  /workloads` (auth)
- `GET  /metrics/summary?workload_id=&window=` (auth) — cached aggregations.
- `GET  /alerts` (auth) — includes summary, severity, detector.

## Conventions
- Type hints everywhere; pydantic schemas separate from ORM models;
  one router module per resource; config via env vars (pydantic-settings).
- Migrations via Alembic — never auto-create tables in prod paths.
- Frontend: typed API client in src/api; components dumb, pages own fetching.
- Conventional commits. Work on a `phase-3` branch.
- CI must pass (lint + tests) before any deploy step.

## Working agreement for Claude Code
- Tackle one task at a time; confirm the stack runs (locally, then deployed)
  before moving on.
- Follow the 3a -> 3b -> 3c order strictly.
- When a task is ambiguous, propose the smallest reasonable interpretation and proceed.
- Do not pull future/out-of-scope work forward to "future-proof."
