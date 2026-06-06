"""Synthetic workload simulator.

Posts MetricSamples to the dashboard API for a few simulated AI workloads,
with realistic latency jitter, occasional errors, and periodic latency spikes
that trip the backend's threshold alerts. No real LLM calls are made — the
point is to give the dashboard live data to visualize.

Config via env:
  API_URL          base URL of the backend (default http://localhost:8000)
  ADMIN_USERNAME   login user (default admin)
  ADMIN_PASSWORD   login password (default admin)
  SIM_INTERVAL     seconds between samples (default 1.0)
  SIM_ITERATIONS   number of samples to post, 0 = run forever (default 0)
"""
import os
import random
import sys
import time

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
INTERVAL = float(os.environ.get("SIM_INTERVAL", "1.0"))
MAX_ITERATIONS = int(os.environ.get("SIM_ITERATIONS", "0"))

# name, base latency (ms), jitter (ms), error_rate, spike_rate, token range
WORKLOADS = [
    {"name": "gpt-4o-chat", "base": 350, "jitter": 150, "error_rate": 0.03,
     "spike_rate": 0.04, "tokens": (200, 1200)},
    {"name": "claude-summarizer", "base": 220, "jitter": 80, "error_rate": 0.02,
     "spike_rate": 0.03, "tokens": (150, 800)},
    {"name": "embeddings-batch", "base": 90, "jitter": 40, "error_rate": 0.05,
     "spike_rate": 0.02, "tokens": (50, 400)},
]


def login(client: httpx.Client) -> dict[str, str]:
    resp = client.post(
        f"{API_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def wait_for_backend(client: httpx.Client, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            if client.get(f"{API_URL}/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"backend at {API_URL} did not become healthy in time")


def make_sample(wl: dict) -> dict:
    if random.random() < wl["spike_rate"]:
        latency = random.randint(1200, 4000)  # above the 1000ms alert threshold
    else:
        latency = max(1, int(random.gauss(wl["base"], wl["jitter"])))
    status = "error" if random.random() < wl["error_rate"] else "ok"
    lo, hi = wl["tokens"]
    tokens = random.randint(lo, hi) if status == "ok" else None
    return {
        "workload": wl["name"],
        "latency_ms": latency,
        "status": status,
        "tokens": tokens,
    }


def main() -> None:
    with httpx.Client(timeout=5.0) as client:
        wait_for_backend(client)
        headers = login(client)
        print(
            f"[simulator] logged in to {API_URL}; "
            f"streaming metrics for {len(WORKLOADS)} workloads",
            flush=True,
        )

        count = 0
        while True:
            payload = make_sample(random.choice(WORKLOADS))
            try:
                resp = client.post(
                    f"{API_URL}/metrics", json=payload, headers=headers
                )
                if resp.status_code == 401:  # token expired -> re-login and retry
                    headers = login(client)
                    continue
                resp.raise_for_status()
                triggered = resp.json().get("triggered_alerts", [])
                flag = f"  ALERT: {triggered[0]['rule']}" if triggered else ""
                print(
                    f"[simulator] {payload['workload']:18} "
                    f"{payload['latency_ms']:5}ms {payload['status']:5}{flag}",
                    flush=True,
                )
            except httpx.HTTPError as exc:
                print(f"[simulator] post failed: {exc}", file=sys.stderr, flush=True)

            count += 1
            if MAX_ITERATIONS and count >= MAX_ITERATIONS:
                print(f"[simulator] done after {count} samples", flush=True)
                return
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
