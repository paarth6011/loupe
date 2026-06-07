# Vision — what Loupe becomes when it's done

> **Loupe** — *a clear look at what your LLM calls really cost.*

> This describes the **target end-state**, not today's code. For what works right
> now, see **[README.md](README.md)**; for the steps to get here, see
> **[ROADMAP.md](ROADMAP.md)**.

## In one line

**Open-source observability for LLM applications** — see the latency, **token
usage, cost, and errors** of your AI calls over time, get alerted (with
plain-English explanations) when something goes wrong, and self-host it all for
**$0 with no API key required**.

## The problem it solves

Teams are shipping more and more features on top of LLMs, but they're flying
blind: How much are we spending, and on which features? Which model is slow
today? Are we getting rate-limited? Did that prompt change blow up our token
usage? General-purpose monitoring tools (uptime checkers, APM) don't understand
tokens, cost, or provider-specific failures — and the vendor dashboards stop at
*their* product's boundary. This fills that gap, for any provider, self-hosted,
without lock-in.

## Who it's for

- Developers and small teams running LLM features who want cost + reliability
  visibility without paying for (or sending their data to) a SaaS vendor.
- Anyone who wants a self-hosted, hackable alternative to closed LLM-analytics
  products.

## What it does (the complete feature set)

### 1. Instrument your LLM calls in two lines
A small **SDK** wraps your existing client and automatically records each call's
latency, input/output tokens, computed cost, status, model, and provider — then
ships it to your dashboard. No vendor SDK, no inference added.

```python
from loupe import track
client = track(anthropic.Anthropic(), workload="support-bot")
# use `client` exactly as before — calls are now observed
```

A provider-agnostic ingestion API (`POST /metrics`) means anything can report in
— the SDK, a proxy/gateway, or your own code. HTTP endpoint probing is included
as a secondary source for monitoring LLM gateways/services.

### 2. Cost & token tracking
Per-model pricing tables turn token counts into dollars. See **spend over time**,
**cost per workload/model**, and token throughput — answer "what did this feature
cost us this week, and why."

### 3. Aggregations & live dashboard
A React dashboard with per-workload and per-model views: latency **p50/p95**,
error rate (by type — rate-limit / timeout / content-filter), request volume,
token throughput, and cost — over flexible time windows, updating live.

### 4. Explainable alerting
- **Threshold rules** (latency, error rate, cost) evaluated on ingest.
- **Statistical anomaly detection** — rolling-window z-score / EWMA baselines per
  (workload, metric) that flag deviations. **Always explainable**: every alert
  records *which detector fired and why* — no black-box models.
- **Severity** (info / warning / critical), de-duplication, and **automatic
  resolution** when conditions recover.

### 5. AI incident summaries (optional, $0-capable)
When an alert fires, generate a concise plain-English "what happened" summary
from the alert + recent metrics. **Pluggable**: a deterministic template and
local models (Ollama) run for **free with no API key**; or plug in Claude/OpenAI
for nicer wording at ~$0.0005/alert.

### 6. Notifications
Get alerted where you already work — **webhook / Slack / Discord / email** — on
alert open and resolve, including **cost-spike** alerts ("daily LLM spend over
$X"). An alert nobody sees is useless; this makes the tool work while you don't
watch it.

### 7. Configurable, multi-user, secure
- Add/edit/remove monitored workloads and set per-monitor thresholds **from the
  UI/API** — no editing env vars and restarting.
- Real authentication (no shipped default credentials; refuses to boot insecure).
- A public read-only **status page** for "are my services up."

## Architecture

```
   your app ──(SDK)──┐
   gateway/proxy ────┤
   HTTP prober ──────┴──▶  POST /metrics ──▶  FastAPI backend ──▶  PostgreSQL
                                                   │   ▲                 │
                                          detection│   │cache            │ aggregate
                                          + alerts  │  Redis             ▼
                                                   ▼                  React dashboard
                                          summaries + notifications        + status page
```

- **Backend:** Python 3.12, FastAPI, SQLAlchemy + Alembic, pydantic.
- **Storage:** PostgreSQL (with retention + downsampling for long history);
  Redis for caching.
- **Frontend:** React + TypeScript + Vite, Recharts.
- **SDK:** thin Python client (more languages later).
- **Detection:** numpy/scipy z-score / EWMA — explainable, no opaque ML.

## Getting started (the experience we're building toward)

```bash
docker compose up        # db + redis + backend + frontend — runs for $0, no key
```
Open the dashboard, create an admin password on first run, drop the SDK into your
app, and watch real latency/token/cost data appear. Self-hosted, your data stays
yours.

## Cost & no lock-in

The tool runs **fully free with no API key**. Cost tracking is computed locally
from public pricing tables. AI summaries default to a free template/local model.
Monitoring your LLM usage adds **$0** in API fees — it observes calls you already
make. (See [README → Costs & API keys](README.md#costs--api-keys).) Optional
cloud hosting incurs normal infrastructure cost; self-hosting with Docker is free.

## What it is *not*

Not a Datadog replacement, not multi-region/HA, not an enterprise RBAC suite, not
a paid SaaS. The guiding principle is **the smallest thing that genuinely helps,
is testable, and is explainable** — focused on LLM observability for individuals
and small teams.

## Status

Today the core pipeline (ingest → aggregate → alert → summarize → visualize)
works end-to-end on real data, with auth, caching, Docker Compose, and CI. The
LLM-specific data model, cost tracking, the SDK, notifications, statistical
detection, and configurable monitors are the in-progress path to this vision —
tracked in **[ROADMAP.md](ROADMAP.md)**.
