from types import SimpleNamespace

import pytest

from loupe import Reporter, track


class CapturingReporter:
    def __init__(self):
        self.calls = []

    def report(self, **fields):
        self.calls.append(fields)


class FakeAnthropicMessages:
    def __init__(self, resp=None, raise_exc=None):
        self._resp = resp
        self._raise = raise_exc

    def create(self, **kwargs):
        if self._raise:
            raise self._raise
        return self._resp


class FakeAnthropicClient:
    def __init__(self, resp=None, raise_exc=None):
        self.messages = FakeAnthropicMessages(resp, raise_exc)
        self.base_url = "https://api.anthropic.com"


def test_track_anthropic_reports_ok():
    resp = SimpleNamespace(
        model="claude-haiku-4-5",
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
    )
    rep = CapturingReporter()
    client = track(
        FakeAnthropicClient(resp), workload="bot", reporter=rep, provider="anthropic"
    )

    out = client.messages.create(model="claude-haiku-4-5", messages=[])

    assert out is resp
    (call,) = rep.calls
    assert call["status"] == "ok"
    assert call["workload"] == "bot"
    assert call["provider"] == "anthropic"
    assert call["model"] == "claude-haiku-4-5"
    assert call["input_tokens"] == 120
    assert call["output_tokens"] == 30
    assert call["latency_ms"] >= 0


def test_track_anthropic_reports_error_and_reraises():
    class RateLimitError(Exception):
        pass

    rep = CapturingReporter()
    client = track(
        FakeAnthropicClient(raise_exc=RateLimitError("429 too many requests")),
        workload="bot",
        reporter=rep,
        provider="anthropic",
    )

    with pytest.raises(RateLimitError):
        client.messages.create(model="claude-haiku-4-5")

    assert rep.calls[0]["status"] == "error"
    assert rep.calls[0]["error_type"] == "rate_limit"


def test_track_openai_reports_ok():
    resp = SimpleNamespace(
        model="gpt-4o",
        usage=SimpleNamespace(prompt_tokens=200, completion_tokens=50),
    )

    class FakeCompletions:
        def create(self, **kw):
            return resp

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self):
            self.chat = FakeChat()

    rep = CapturingReporter()
    client = track(FakeOpenAI(), workload="oa", reporter=rep, provider="openai")

    out = client.chat.completions.create(model="gpt-4o", messages=[])

    assert out is resp
    call = rep.calls[0]
    assert call["provider"] == "openai"
    assert call["model"] == "gpt-4o"
    assert call["input_tokens"] == 200
    assert call["output_tokens"] == 50


def test_passthrough_for_unwrapped_attributes():
    resp = SimpleNamespace(model="m", usage=None)
    rep = CapturingReporter()
    client = track(
        FakeAnthropicClient(resp), workload="b", reporter=rep, provider="anthropic"
    )
    # An attribute we don't wrap still reaches the underlying client.
    assert client.base_url == "https://api.anthropic.com"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        track(object(), workload="x", reporter=CapturingReporter())


class FakeHttpClient:
    def __init__(self):
        self.posts = []

    def post(self, url, json=None, headers=None):
        self.posts.append((url, json, headers))
        return SimpleNamespace(status_code=201, json=lambda: {})


def test_reporter_uses_api_key_header_and_skips_login():
    rep = Reporter(url="http://x", api_key="loupe_sk_test")
    rep._client = FakeHttpClient()
    rep._send({"workload": "w", "latency_ms": 1, "status": "ok"})

    posts = rep._client.posts
    assert len(posts) == 1  # no login round-trip
    url, _, headers = posts[0]
    assert url.endswith("/metrics")
    assert headers == {"X-API-Key": "loupe_sk_test"}
    assert all("/auth/login" not in p[0] for p in posts)
