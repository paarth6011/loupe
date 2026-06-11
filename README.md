# 🔎 Loupe

**Open-source observability for LLM apps** — track the latency, tokens, and cost
of your AI calls, with explainable alerts and plain-English incident summaries.
Self-hosted, runs for $0, no API key required.

A loupe is the magnifier you use to inspect fine detail — this one shows you what
every LLM call really costs.

> **Status:** the full pipeline works today on real data — ingest → aggregate →
> alert → summarize → visualize, including LLM cost/token tracking and the
> two-line instrumentation SDK. See **[VISION.md](VISION.md)** for the vision and
> **[ROADMAP.md](ROADMAP.md)** for what's next.

## Demo

![Loupe walkthrough — dashboard, cost breakdown, per-workload monitors, one-click alert resolve, and the public status page](docs/demo.gif)

<details>
<summary>Individual screenshots</summary>

| Dashboard (latency · tokens · cost · alerts) | Public status page |
|---|---|
| ![Loupe dashboard](docs/screenshots/dashboard.png) | ![Loupe status page](docs/screenshots/status-page.png) |

</details>

## Quickstart

```bash
cp .env.example .env        # optional — sensible defaults are baked in
docker compose up --build   # brings up db + backend + frontend (empty instance)
```

Then open **http://localhost:5173**. In local dev you're signed in
automatically — no login screen; a deployed instance (`ENVIRONMENT=production`)
requires a real login and refuses to boot on the default password. The instance
starts empty — instrument an app with the [SDK](#instrument-your-llm-calls-sdk)
to fill it with your own data.

**Want a live demo first?** Start the optional prober, which measures real public
HTTP endpoints (latency + up/down) so the charts and alerts populate within
seconds:

```bash
docker compose --profile demo up -d   # adds the prober (canned demo data)
```

## Instrument your LLM calls (SDK)

The [`loupe` Python SDK](sdk/) wraps your Anthropic/OpenAI client so each call's
latency, tokens, cost, and errors flow into Loupe — in two lines:

```python
from loupe import track
client = track(anthropic.Anthropic(), workload="support-bot")
# use `client` exactly as before — calls are now observed
```

Create a per-source ingestion key in the dashboard (**🔑 API keys**) and set
`LOUPE_API_KEY` so the SDK authenticates without the admin password.

## Services & ports

| Service     | URL / port              | What it is                                 |
|-------------|-------------------------|--------------------------------------------|
| frontend    | http://localhost:5173   | React + TypeScript dashboard (nginx)       |
| backend     | http://localhost:8000   | FastAPI API (`/docs` for Swagger UI)       |
| db          | localhost:5432          | PostgreSQL 16                              |
| redis       | localhost:6379          | Redis 7 (caches `/metrics/summary`)        |
| prober      | —                       | Probes real HTTP endpoints (latency + up/down) |

The backend runs `alembic upgrade head` on startup, so the schema is created
automatically on first boot.

## API surface

- `GET  /health`
- `POST /auth/login` → JWT
- `POST /metrics` (auth: API key via `X-API-Key`, or admin JWT) — ingest a sample; evaluates thresholds on insert
- `POST /apikeys` · `GET /apikeys` · `DELETE /apikeys/{id}` (admin JWT) — manage ingestion keys
- `GET  /workloads` (auth)
- `PATCH /workloads/{id}` (auth) — publish/unpublish a workload on the status page
- `GET  /status` (**no auth**) — public status page: health of published workloads only
- `GET  /metrics/summary?workload_id=&window=` (auth) — p50/p95, error rate, count, tokens, cost
- `GET  /metrics/timeseries?workload_id=&window=&bucket=` (auth) — bucketed latency/errors + tokens/cost
- `GET  /metrics/cost?window=` (auth) — account-wide spend, broken down by model and workload
- `GET  /alerts` (auth) — supports `?workload_id=` and `?resolved=` filters
- `POST /alerts/{id}/resolve` · `POST /alerts/{id}/reopen` (auth) — manually resolve an alert (e.g. one whose workload went quiet) or undo that
- `GET  /workloads/{id}/monitors` (auth) — every rule's effective config for a workload
- `PUT  /workloads/{id}/monitors/{rule}` (auth) — enable/disable or override a rule's threshold
- `POST /auth/stream-ticket` (auth) — exchange the admin token for a short-lived, read-only ticket for the live stream
- `GET  /events?ticket=<ticket>` — Server-Sent Events stream; pushes a `changed` event when new data lands so the dashboard refetches without fixed-interval polling

## Tests

```bash
docker compose exec backend python -m pytest -q
```

## Configuration

All config is via environment variables (see `.env.example`): database URL, JWT
settings, the single admin user, and the alerting thresholds
(`LATENCY_THRESHOLD_MS`, `ERROR_RATE_THRESHOLD`, …).

**LLM-tuned alerts** add three rules on top of latency/error-rate, evaluated on
ingest and tunable via env vars:

| Rule | Fires when | Threshold var |
|---|---|---|
| `cost_spike` | a single call costs more than the ceiling | `COST_PER_REQUEST_THRESHOLD_USD` (default `1.0`) |
| `token_spike` | a single call uses more tokens (in+out) than the ceiling | `TOKEN_PER_REQUEST_THRESHOLD` (default `100000`) |
| `rate_limit_surge` | a share of recent calls are provider 429s | `RATE_LIMIT_THRESHOLD` (default `0.2`) |

These read the LLM sample fields and stay dormant for HTTP-only workloads, where
those fields are null.

**Statistical anomaly detection** complements the fixed thresholds: a rolling
per-workload **z-score** baseline catches latency/cost that is abnormal *for that
workload* even when it's under the absolute ceiling (e.g. a service usually at
50 ms jumping to 300 ms). It's explainable by design — every anomaly alert is
tagged with its `detector` (`zscore`) and spells out the numbers: recent mean,
the learned baseline mean ± σ, and the sample count. No black-box models.

| Rule | Fires when | Detector |
|---|---|---|
| `latency_anomaly` | recent latency is ≥ N σ above the workload's baseline | `zscore` |
| `cost_anomaly` | recent per-call cost is ≥ N σ above the workload's baseline | `zscore` |

Tunable via `ANOMALY_Z_THRESHOLD` (default `3.0`), `ANOMALY_RECENT_SAMPLES`,
`ANOMALY_MIN_BASELINE`, and `ANOMALY_BASELINE_WINDOW`.

**Per-workload monitors:** the env vars above set the *global defaults*. Each
workload can override any rule's threshold or disable it entirely — at runtime,
no redeploy — via the **⚙ Monitors** modal in the dashboard or the
`/workloads/{id}/monitors` API. Disabling a rule mutes it and clears its active
alerts; an empty threshold falls back to the global default.

**Data retention:** set `RETENTION_DAYS` (default `0` = keep forever) to prune
metric samples and stale resolved alerts older than that many days. A background
sweep runs every `RETENTION_SWEEP_HOURS`; `POST /admin/prune?days=N` (admin)
triggers it on demand. Aggregation (summary, cost, timeseries) runs in SQL, so
these endpoints scale with the table rather than loading it into the app.

**Public status page:** a no-auth page at **`/status`** (data from `GET /status`)
shows the health of workloads you explicitly publish — operational / degraded /
down / unknown, plus 24h uptime and p50 latency. Status is derived the same
explainable way as alerts (an open critical alert is an outage, an open warning
is a degradation, a workload that stopped reporting is "unknown"), and the page
never exposes cost, tokens, or alert detail. Workloads are opt-in: flip the
**Public** toggle next to a workload in the dashboard (which calls
`PATCH /workloads/{id}`). Nothing is published by default.

**Live updates:** the dashboard subscribes to a single `GET /events`
Server-Sent Events stream and refetches only when the server signals new data
(it watches the newest sample/alert id and the open-alert count), instead of
blindly polling. Because `EventSource` can't send an `Authorization` header, the
dashboard first exchanges its token for a short-lived, read-only **stream
ticket** and passes that in the query string — so the full admin token never
lands in a URL or proxy log. Each connection self-recycles every few minutes and
the client reconnects with a fresh ticket.

**Alert notifications:** set `NOTIFY_WEBHOOK_URL` to a Slack/Discord/generic
webhook to get pinged when an alert fires or resolves. The payload includes
`text` (Slack), `content` (Discord), and structured `alert` fields; empty
disables notifications.

## Costs & API keys

**This project runs fully for $0 with no API key.** Keys are optional, used in
exactly one place, and even there the cost is a rounding error.

| Capability | Needs a key? | Who pays | Cost |
|---|---|---|---|
| Run the whole stack (Docker Compose) | No | — | **$0** |
| Monitoring your LLM/HTTP workloads | No | — | **$0 added** — the tool *observes* calls you already make; the ingest path adds zero inference |
| Cost tracking (tokens → dollars) | No | — | **$0** — computed locally from public pricing tables, no API call |
| AI incident summaries (real model vs template) | **Optional** | the deployer | **~$0.0005 / alert** with Claude Haiku — or **$0** with the built-in template / a local model |

### The one optional spot: AI incident summaries

The only feature that itself calls an LLM is the plain-English alert summary, and
it's opt-in. `SUMMARY_PROVIDER` chooses the backend behind a single summarizer
interface:

| `SUMMARY_PROVIDER` | Backend | Key? | Cost |
|---|---|---|---|
| `auto` (default) | Claude if `ANTHROPIC_API_KEY` is set, else the template | optional | $0 or ~$0.0005/alert |
| `template` | deterministic, no-API summary | no | **$0** |
| `ollama` | a local Ollama server (`OLLAMA_URL` / `OLLAMA_MODEL`) | no | **$0**, offline |
| `claude` | Anthropic API (degrades to template if no key) | yes | ~$0.0005/alert |

For the **$0 local-model** path: install [Ollama](https://ollama.com), run
`ollama pull llama3.2`, then set `SUMMARY_PROVIDER=ollama`. From the Docker
backend, Ollama on the host is reached at `http://host.docker.internal:11434`
(already the default). If you plug in a Claude key instead, each summary is tiny
(~180 input + ~60 output tokens):

- **~$0.0005 per alert** on Claude Haiku 4.5
- ~**$0.50** per 1,000 alerts/month · ~**$5** per 10,000/month

Alerts are de-duplicated (one summary per alert, not per breach), so an alert
storm doesn't multiply the bill.

### What this tool does *not* cost you

The money people actually spend — their own LLM API usage — is **not** a cost of
this tool. Your app already calls OpenAI/Anthropic and pays for it; the SDK just
records latency / tokens / cost about those calls and adds no inference of its
own. Monitoring a large LLM bill costs **$0 extra** in API fees (and ideally
helps you *reduce* it by showing where the spend goes).

> **Separate from API keys:** deploying to a cloud (e.g. the optional GCP setup
> in `DEPLOYMENT.md`) incurs **infrastructure** cost — Cloud SQL, Memorystore,
> Cloud Run — on the order of tens of dollars/month if left running. Self-hosting
> with Docker Compose avoids this entirely.
