# Changelog

All notable changes to Loupe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — first public release

The initial open-source release: **observability for LLM apps** — track latency,
tokens, and cost per call, with explainable alerts, plain-English incident
summaries, and a live dashboard. Self-hosted, runs for $0, no API key required.

### Added

- **Ingestion & SDK** — a provider-agnostic `POST /metrics` contract and a
  two-line Python SDK (`loupe.track`) that wraps an Anthropic/OpenAI client to
  record latency, tokens, cost, and errors. Per-source ingestion API keys
  (`X-API-Key`), hashed at rest and managed in the dashboard.
- **LLM cost & token tracking** — per-model pricing table computes `cost_usd` on
  ingest (no API call); `/metrics/cost` breaks spend down by model and workload;
  dashboard panels for token throughput and cost over time.
- **Alerting** — threshold rules (latency, error rate) plus LLM-tuned rules
  (`cost_spike`, `token_spike`, `rate_limit_surge`), and explainable statistical
  **anomaly detection** via per-workload rolling z-score baselines
  (`latency_anomaly`, `cost_anomaly`) — every alert records the detector and its
  numbers. Per-workload monitors let you override or disable any rule at runtime.
- **Incident summaries** — plain-English alert summaries via a pluggable
  summarizer: `auto` / `template` ($0, no key) / `claude` / `ollama` (local,
  $0, offline). Webhook notifications (Slack/Discord/generic) on fire & resolve.
- **Dashboard & status page** — React + TypeScript dashboard with live updates
  over **Server-Sent Events** (no more fixed-interval polling), and a public,
  no-auth **status page** (`/status`) showing the health of workloads you opt in
  to publishing — never their cost or alert detail.
- **Scale & operations** — aggregation pushed into SQL (`COUNT`/`SUM`/`GROUP BY`,
  Postgres `percentile_cont`); configurable **data retention** with a background
  sweep and `POST /admin/prune`; Redis-cached summaries; JWT auth that refuses to
  boot on insecure defaults in production.
- **Deploy** — Docker Compose for local dev, multi-stage non-root images for
  backend and frontend, Terraform for an optional GCP (Cloud Run) deploy, and CI
  (lint + tests + build) on every PR.

[Unreleased]: https://github.com/OWNER/loupe/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/loupe/releases/tag/v0.1.0
