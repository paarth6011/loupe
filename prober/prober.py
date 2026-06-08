"""Real HTTP endpoint prober.

Measures genuine latency and availability of configured HTTP endpoints and posts
the results to the dashboard's /metrics API. These are real network round-trips —
no synthetic data. A slow or failing endpoint produces real latency spikes and
real error-rate, which drive the same threshold alerts as any other workload.

Config via env:
  API_URL          dashboard backend base URL (default http://localhost:8000)
  ADMIN_USERNAME / ADMIN_PASSWORD   login creds
  PROBE_INTERVAL   seconds between probe rounds (default 5)
  PROBE_TIMEOUT    per-request timeout in seconds (default 5)
  PROBE_TARGETS    "name=url,name=url,..." (defaults to a built-in set)
  PROBE_ITERATIONS number of rounds to run, 0 = forever (default 0)
"""
import os
import sys
import time

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
INTERVAL = float(os.environ.get("PROBE_INTERVAL", "5"))
TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "5"))
MAX_ROUNDS = int(os.environ.get("PROBE_ITERATIONS", "0"))

# Real, well-known endpoints with naturally varied latency profiles.
DEFAULT_TARGETS = [
    ("google", "https://www.google.com/generate_204"),
    ("github-api", "https://api.github.com"),
    ("cloudflare", "https://www.cloudflare.com"),
    ("wikipedia", "https://en.wikipedia.org/wiki/Main_Page"),
]


def parse_targets(raw: str) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if part and "=" in part:
            name, url = part.split("=", 1)
            targets.append((name.strip(), url.strip()))
    return targets


TARGETS = parse_targets(os.environ.get("PROBE_TARGETS", "")) or DEFAULT_TARGETS


def login(client: httpx.Client) -> dict[str, str]:
    resp = client.post(
        f"{API_URL}/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=5.0,
    )
    resp.raise_for_status()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def wait_for_backend(client: httpx.Client, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            if client.get(f"{API_URL}/health", timeout=5.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"backend at {API_URL} did not become healthy in time")


def probe(client: httpx.Client, url: str) -> tuple[int, str]:
    """Return (latency_ms, status) for a real HTTP GET. A timeout or connection
    error counts as an error at roughly the timeout latency."""
    start = time.perf_counter()
    try:
        resp = client.get(url, timeout=TIMEOUT, follow_redirects=True)
        latency = int((time.perf_counter() - start) * 1000)
        return latency, "ok" if resp.status_code < 400 else "error"
    except httpx.HTTPError:
        latency = int((time.perf_counter() - start) * 1000)
        return latency, "error"


def main() -> None:
    # Identify ourselves like a real monitor; some servers 403 anonymous clients.
    with httpx.Client(headers={"User-Agent": "loupe-prober/1.0"}) as client:
        wait_for_backend(client)
        headers = login(client)
        print(
            f"[prober] probing {len(TARGETS)} real endpoints -> {API_URL}",
            flush=True,
        )

        rounds = 0
        while True:
            for name, url in TARGETS:
                latency, status = probe(client, url)
                payload = {"workload": name, "latency_ms": latency, "status": status}
                try:
                    resp = client.post(
                        f"{API_URL}/metrics", json=payload, headers=headers, timeout=5.0
                    )
                    if resp.status_code == 401:
                        headers = login(client)
                        continue
                    resp.raise_for_status()
                    triggered = resp.json().get("triggered_alerts", [])
                    flag = f"  ALERT: {triggered[0]['rule']}" if triggered else ""
                    print(
                        f"[prober] {name:14} {latency:5}ms {status:5}{flag}",
                        flush=True,
                    )
                except httpx.HTTPError as exc:
                    print(f"[prober] post failed: {exc}", file=sys.stderr, flush=True)

            rounds += 1
            if MAX_ROUNDS and rounds >= MAX_ROUNDS:
                print(f"[prober] done after {rounds} rounds", flush=True)
                return
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
