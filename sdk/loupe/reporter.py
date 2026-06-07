from __future__ import annotations

import os
import threading

import httpx


class Reporter:
    """Ships metric samples to a Loupe backend.

    Reporting is non-blocking (fire-and-forget on a daemon thread) and never
    raises into the caller's code path — observability must not break the app.
    Authentication is a simple username/password login for now; API keys come
    in a later step.
    """

    def __init__(
        self,
        url: str = "http://localhost:8000",
        username: str = "admin",
        password: str = "admin",
        token: str | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._username = username
        self._password = password
        self._token = token
        self._client = httpx.Client(timeout=timeout)

    @classmethod
    def from_env(cls) -> Reporter:
        return cls(
            url=os.environ.get("LOUPE_URL", "http://localhost:8000"),
            username=os.environ.get("LOUPE_USERNAME", "admin"),
            password=os.environ.get("LOUPE_PASSWORD", "admin"),
            token=os.environ.get("LOUPE_TOKEN"),
        )

    def report(self, **fields) -> None:
        payload = {k: v for k, v in fields.items() if v is not None}
        threading.Thread(target=self._send, args=(payload,), daemon=True).start()

    # -- internals -----------------------------------------------------------

    def _login(self) -> None:
        resp = self._client.post(
            f"{self._url}/auth/login",
            json={"username": self._username, "password": self._password},
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]

    def _post(self, payload: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        return self._client.post(f"{self._url}/metrics", json=payload, headers=headers)

    def _send(self, payload: dict) -> None:
        try:
            if not self._token:
                self._login()
            resp = self._post(payload)
            if resp.status_code == 401:  # token expired -> re-login and retry once
                self._login()
                self._post(payload)
        except Exception:
            pass  # swallow — never break the caller
