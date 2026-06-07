# loupe (Python SDK)

Instrument your LLM calls and ship latency, tokens, cost, and errors to a
[Loupe](../README.md) backend — in two lines.

```bash
pip install loupe   # (from this repo for now: pip install ./sdk)
```

```python
import anthropic
from loupe import track

client = track(anthropic.Anthropic(), workload="support-bot")
# use `client` exactly as before — every call is now observed
resp = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=200,
    messages=[{"role": "user", "content": "hi"}],
)
```

Works the same for OpenAI:

```python
from openai import OpenAI
client = track(OpenAI(), workload="rag-pipeline")
client.chat.completions.create(model="gpt-4o", messages=[...])
```

## Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `LOUPE_URL` | `http://localhost:8000` | Loupe backend URL |
| `LOUPE_USERNAME` / `LOUPE_PASSWORD` | `admin` / `admin` | login for now (API keys later) |
| `LOUPE_TOKEN` | — | use a pre-obtained bearer token instead of login |

Or pass a configured `Reporter`:

```python
from loupe import Reporter, track
client = track(anthropic.Anthropic(), workload="bot",
               reporter=Reporter(url="https://loupe.internal"))
```

## Notes

- **Non-blocking & safe:** reporting happens on a background thread and never
  raises into your code — if Loupe is down, your LLM calls are unaffected.
- **Cost** is computed by the backend from the model + token counts (you don't
  need to send it).
- v1 covers synchronous `messages.create` (Anthropic) and
  `chat.completions.create` (OpenAI). Async and streaming are on the roadmap.
- Pass `provider="anthropic"|"openai"` if auto-detection can't identify a client.
