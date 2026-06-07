# 🔎 Loupe

**Open-source observability for LLM apps** — track the latency, tokens, and cost
of your AI calls, with explainable alerts and plain-English incident summaries.
Self-hosted, runs for $0, no API key required.

A loupe is the magnifier you use to inspect fine detail — this one shows you what
every LLM call really costs.

> **Status:** the core monitoring pipeline (ingest → aggregate → alert →
> summarize → visualize) works today on real data, as described below. The
> LLM-specific cost/token tracking and the instrumentation SDK are in progress —
> see **[VISION.md](VISION.md)** for the finished picture and
> **[ROADMAP.md](ROADMAP.md)** for the path.

## Quickstart

```bash
cp .env.example .env        # optional — sensible defaults are baked in
docker compose up --build   # brings up db + backend + frontend + prober
```

Then open **http://localhost:5173** and sign in with **admin / admin**.

The prober immediately starts measuring real HTTP endpoints (latency + up/down),
so the charts and alerts populate within seconds.

## Instrument your LLM calls (SDK)

The [`loupe` Python SDK](sdk/) wraps your Anthropic/OpenAI client so each call's
latency, tokens, cost, and errors flow into Loupe — in two lines:

```python
from loupe import track
client = track(anthropic.Anthropic(), workload="support-bot")
# use `client` exactly as before — calls are now observed
```

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
- `POST /metrics` (auth) — ingest a sample; evaluates thresholds on insert
- `GET  /workloads` (auth)
- `GET  /metrics/summary?workload_id=&window=` (auth) — p50/p95, error rate, count, tokens, cost
- `GET  /metrics/timeseries?workload_id=&window=&bucket=` (auth) — bucketed latency/errors + tokens/cost
- `GET  /metrics/cost?window=` (auth) — account-wide spend, broken down by model and workload
- `GET  /alerts` (auth) — supports `?workload_id=` and `?resolved=` filters

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
it's opt-in. With no `ANTHROPIC_API_KEY` set it uses a **deterministic template
($0, no key)**; a local model (e.g. Ollama) is also $0. If you plug in a key for
nicer summaries, each one is tiny (~180 input + ~60 output tokens):

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
