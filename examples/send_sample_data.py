"""Send a few sample metrics to a running Loupe instance — no SDK, no API key
for an LLM provider, just the Python standard library.

Use it to see the pipeline work end to end before instrumenting a real app.

    # 1. Create an ingestion key in the dashboard (API keys panel), then:
    export LOUPE_URL=http://localhost:8000
    export LOUPE_API_KEY=loupe_sk_...
    # 2. Run it:
    python3 examples/send_sample_data.py

Refresh the dashboard and select the "my-app" workload to see the data.
"""

import json
import os
import random
import urllib.request

LOUPE_URL = os.environ.get("LOUPE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("LOUPE_API_KEY")
WORKLOAD = os.environ.get("LOUPE_WORKLOAD", "my-app")
COUNT = int(os.environ.get("LOUPE_COUNT", "30"))


def send(sample):
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(
        LOUPE_URL + "/metrics",
        data=json.dumps(sample).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status


def main():
    if not API_KEY:
        raise SystemExit(
            "Set LOUPE_API_KEY to an ingestion key from the dashboard first."
        )
    sent = 0
    for _ in range(COUNT):
        is_error = random.random() < 0.1
        sample = {
            "workload": WORKLOAD,
            # A slow tail on errors, so the latency chart has shape.
            "latency_ms": random.randint(1700, 2600)
            if is_error
            else random.randint(350, 1400),
            "status": "error" if is_error else "ok",
            "model": "claude-opus-4-8",
            "provider": "anthropic",
            "input_tokens": random.randint(200, 1200),
            "output_tokens": random.randint(50, 600),
        }
        if is_error:
            sample["error_type"] = "timeout"
        try:
            if send(sample) == 201:
                sent += 1
        except Exception as exc:  # noqa: BLE001 — best-effort demo script
            print("failed to send:", exc)
    print(f"sent {sent}/{COUNT} samples for '{WORKLOAD}' — refresh the dashboard")


if __name__ == "__main__":
    main()
