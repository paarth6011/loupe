# Loupe — Roadmap

## Vision

**Loupe: open-source observability for LLM apps.** Drop a small SDK around your AI calls
and see latency, **token usage, and cost** per model/provider over time, with
threshold + anomaly alerts and plain-English incident summaries.

The differentiator is the AI/LLM focus: general uptime tools don't track tokens,
cost, or provider-specific error types. The data comes from *users instrumenting
their own apps* (their keys, their cost) — the tool only observes and adds no
inference of its own. See **[README → Costs & API keys](README.md#costs--api-keys)**:
it runs fully for $0 with no API key.

## Where it is today

A working full-stack monitoring stack: FastAPI + Postgres + Redis backend, React
dashboard, an HTTP endpoint prober, threshold alerting with severity, auto-
resolution, LLM incident summaries (pluggable, with a $0 template fallback), JWT
auth, Docker Compose, and Terraform for an optional GCP deploy. The `POST /metrics`
contract is provider-agnostic, so the pivot below is mostly additive.

## Table stakes (needed before this is real OSS)

- [x] `LICENSE` (MIT)
- [x] `CONTRIBUTING.md`, `SECURITY.md`
- [x] CI (tests + build on PRs)
- [x] Refuse to boot in production with default credentials (`admin`/`admin`,
      `change-me` JWT secret) — enforced via `ENVIRONMENT=production`
- [ ] Published, versioned container images (GHCR) + tagged releases
- [x] Lint/format in CI (ruff, prettier)
- [ ] Configurable monitors/thresholds via the UI/API (not just env vars)
- [x] Notifications — webhook (Slack/Discord/generic) on alert fire & resolve
      (`NOTIFY_WEBHOOK_URL`); email/native channels later

## LLM-observability features (the niche)

- [x] Enrich `MetricSample`: `model`, `provider`, `input_tokens`, `output_tokens`,
      `cost_usd`, `operation`, `error_type` (migration 0003) — all nullable, so
      HTTP probes and the existing contract are unaffected
- [x] Cost tracking: per-model pricing table → auto-compute `cost_usd` on ingest;
      cost/token rollups in `/metrics/summary`; `GET /metrics/cost` breakdown by
      model + workload (spend-over-time charts come with the dashboard step)
- [x] A Python SDK (`sdk/`): wrap an Anthropic/OpenAI client to auto-record
      latency/tokens/cost/errors (`track(anthropic.Anthropic(), workload="…")`);
      non-blocking, safe. Async/streaming still to come.
- [x] Dashboard panels for token throughput and cost-over-time (per selected
      workload) plus an account-wide spend breakdown by model and workload
      (`GET /metrics/cost`); the timeseries endpoint now also returns per-bucket
      tokens + cost
- [x] LLM-tuned alerts: `cost_spike` (per-call $ ceiling), `token_spike` (per-call
      token ceiling), `rate_limit_surge` (clustered 429s). Threshold-based and
      dormant for HTTP workloads; per-workload statistical baselines are next
- [ ] Pluggable summarizer incl. local models (Ollama) so the AI feature is $0
- [ ] Public read-only status page

## Scale / correctness (before heavy real use)

- [ ] Push aggregation into SQL (today it loads samples into Python) + data
      retention and downsampling (e.g. TimescaleDB / continuous aggregates)
- [ ] Live updates via SSE/WebSocket instead of polling
- [ ] Keep the core cloud-agnostic; treat GCP/Terraform as one deploy example

## Explicitly out of scope (for now)

Multi-region / HA failover, enterprise RBAC, multi-cloud, paid integrations.
Keep it the smallest thing that genuinely helps and is explainable.
