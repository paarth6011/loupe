from __future__ import annotations

import atexit
import os
import queue
import threading

import httpx

# Bounded so a misbehaving/offline backend can't grow memory without limit; we
# shed load rather than block the caller's hot path.
_MAX_QUEUE = 10_000


class Reporter:
    """Ships metric samples to a Loupe backend.

    Reporting is non-blocking and never raises into the caller's code path —
    observability must not break the app. Samples are enqueued and drained by a
    single background worker, which (a) bounds resource use no matter the call
    rate, (b) serializes login/token handling, and (c) can be flushed at exit so
    short-lived scripts don't lose their final samples.

    Auth, in order of preference:
      1. ``api_key`` — a revocable ingestion key (recommended; sent as
         ``X-API-Key``). No login round-trip.
      2. ``token`` — a pre-obtained bearer JWT.
      3. ``username`` / ``password`` — admin login, exchanged for a JWT.
    """

    def __init__(
        self,
        url: str = "http://localhost:8000",
        username: str = "admin",
        password: str = "admin",
        token: str | None = None,
        api_key: str | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._username = username
        self._password = password
        self._token = token
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout)
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=_MAX_QUEUE)
        self._login_lock = threading.Lock()
        self._worker = threading.Thread(
            target=self._run, name="loupe-reporter", daemon=True
        )
        self._worker.start()
        # Best-effort drain at interpreter exit so a script that reports then
        # exits immediately doesn't drop its last samples.
        atexit.register(self.flush)

    @classmethod
    def from_env(cls) -> Reporter:
        return cls(
            url=os.environ.get("LOUPE_URL", "http://localhost:8000"),
            username=os.environ.get("LOUPE_USERNAME", "admin"),
            password=os.environ.get("LOUPE_PASSWORD", "admin"),
            token=os.environ.get("LOUPE_TOKEN"),
            api_key=os.environ.get("LOUPE_API_KEY"),
        )

    def report(self, **fields) -> None:
        """Enqueue a sample for delivery. Non-blocking; drops under extreme
        backpressure rather than stalling the caller."""
        payload = {k: v for k, v in fields.items() if v is not None}
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            pass  # backend unreachable/slow — shed load, never block the app

    def flush(self, timeout: float = 3.0) -> None:
        """Wait (up to ``timeout`` seconds) for queued samples to be sent.
        Bounded so it can't hang process exit if the backend is unresponsive."""
        waiter = threading.Thread(target=self._queue.join, daemon=True)
        waiter.start()
        waiter.join(timeout)

    # -- internals -----------------------------------------------------------

    def _run(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                self._send(payload)
            finally:
                self._queue.task_done()

    def _login(self) -> None:
        resp = self._client.post(
            f"{self._url}/auth/login",
            json={"username": self._username, "password": self._password},
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def _post(self, payload: dict) -> httpx.Response:
        if self._api_key:
            headers = {"X-API-Key": self._api_key}
        elif self._token:
            headers = {"Authorization": f"Bearer {self._token}"}
        else:
            headers = {}
        return self._client.post(f"{self._url}/metrics", json=payload, headers=headers)

    def _send(self, payload: dict) -> None:
        try:
            # API keys don't expire and need no login handshake.
            if self._api_key:
                self._post(payload)
                return
            if not self._token:
                with self._login_lock:
                    if not self._token:
                        self._login()
            resp = self._post(payload)
            if resp.status_code == 401:  # token expired -> re-login and retry once
                with self._login_lock:
                    self._login()
                self._post(payload)
        except Exception:
            pass  # swallow — never break the caller
