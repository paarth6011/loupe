# Roadmap

## Vision

**Open-source observability for LLM apps.** Drop a small SDK around your AI calls
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
- [ ] Remove default credentials (`admin`/`admin`, `change-me` JWT secret) — force a
      generated/first-run secret; refuse to boot with defaults in prod
- [ ] Published, versioned container images (GHCR) + tagged releases
- [ ] Lint/format in CI (ruff, prettier)
- [ ] Configurable monitors/thresholds via the UI/API (not just env vars)
- [ ] Notifications (Slack / Discord / email / webhook) — an alert nobody sees is useless

## LLM-observability features (the niche)

- [ ] Enrich `MetricSample`: `model`, `provider`, `input_tokens`, `output_tokens`,
      `cost_usd`, `operation`, error type (rate-limit / timeout / content-filter)
- [ ] Cost tracking: per-model pricing table → spend over time, per model/workload
- [ ] A Python SDK: wrap an LLM client to auto-record latency/tokens/cost/errors
      (`client = track(anthropic.Anthropic(), workload="support-bot")`)
- [ ] Dashboard panels for token throughput and cost-over-time; per-model breakdown
- [ ] LLM-tuned alerts: cost spikes, rate-limit surges, token anomalies
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
