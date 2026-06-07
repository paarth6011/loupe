from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from loupe.reporter import Reporter


@dataclass
class _Ctx:
    reporter: Reporter
    workload: str
    provider: str


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _classify_error(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "ratelimit" in name or "rate limit" in text or "429" in text:
        return "rate_limit"
    if "timeout" in name or "timeout" in text:
        return "timeout"
    if "content" in text and "filter" in text:
        return "content_filter"
    return "error"


def _extract_anthropic(resp: Any) -> tuple[int | None, int | None, str | None]:
    usage = getattr(resp, "usage", None)
    return (
        getattr(usage, "input_tokens", None) if usage else None,
        getattr(usage, "output_tokens", None) if usage else None,
        getattr(resp, "model", None),
    )


def _extract_openai(resp: Any) -> tuple[int | None, int | None, str | None]:
    usage = getattr(resp, "usage", None)
    return (
        getattr(usage, "prompt_tokens", None) if usage else None,
        getattr(usage, "completion_tokens", None) if usage else None,
        getattr(resp, "model", None),
    )


def _instrument(
    ctx: _Ctx,
    model: str | None,
    call: Callable[[], Any],
    extract: Callable[[Any], tuple[int | None, int | None, str | None]],
) -> Any:
    start = time.perf_counter()
    try:
        resp = call()
    except Exception as exc:
        ctx.reporter.report(
            workload=ctx.workload,
            latency_ms=_ms(start),
            status="error",
            model=model,
            provider=ctx.provider,
            error_type=_classify_error(exc),
        )
        raise
    in_tokens, out_tokens, used_model = extract(resp)
    ctx.reporter.report(
        workload=ctx.workload,
        latency_ms=_ms(start),
        status="ok",
        model=used_model or model,
        provider=ctx.provider,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
    )
    return resp


# --- Transparent proxies that intercept the leaf `.create()` call -----------


class _Proxy:
    """Forwards every attribute to the wrapped object."""

    def __init__(self, inner: Any) -> None:
        self.__dict__["_inner"] = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _AnthropicMessages(_Proxy):
    def __init__(self, inner: Any, ctx: _Ctx) -> None:
        super().__init__(inner)
        self.__dict__["_ctx"] = ctx

    def create(self, **kwargs: Any) -> Any:
        return _instrument(
            self._ctx,
            kwargs.get("model"),
            lambda: self._inner.create(**kwargs),
            _extract_anthropic,
        )


class _AnthropicClient(_Proxy):
    def __init__(self, inner: Any, ctx: _Ctx) -> None:
        super().__init__(inner)
        self.__dict__["messages"] = _AnthropicMessages(inner.messages, ctx)


class _OpenAICompletions(_Proxy):
    def __init__(self, inner: Any, ctx: _Ctx) -> None:
        super().__init__(inner)
        self.__dict__["_ctx"] = ctx

    def create(self, **kwargs: Any) -> Any:
        return _instrument(
            self._ctx,
            kwargs.get("model"),
            lambda: self._inner.create(**kwargs),
            _extract_openai,
        )


class _OpenAIChat(_Proxy):
    def __init__(self, inner: Any, ctx: _Ctx) -> None:
        super().__init__(inner)
        self.__dict__["completions"] = _OpenAICompletions(inner.completions, ctx)


class _OpenAIClient(_Proxy):
    def __init__(self, inner: Any, ctx: _Ctx) -> None:
        super().__init__(inner)
        self.__dict__["chat"] = _OpenAIChat(inner.chat, ctx)


def _detect_provider(client: Any) -> str | None:
    module = type(client).__module__.lower()
    if "anthropic" in module:
        return "anthropic"
    if "openai" in module:
        return "openai"
    return None


def track(
    client: Any,
    workload: str,
    reporter: Reporter | None = None,
    provider: str | None = None,
) -> Any:
    """Wrap an Anthropic or OpenAI client so each call is observed by Loupe.

    Use the returned object exactly like the original client. Pass `provider`
    explicitly if auto-detection can't identify the client.
    """
    reporter = reporter or Reporter.from_env()
    provider = provider or _detect_provider(client)
    if provider == "anthropic":
        return _AnthropicClient(client, _Ctx(reporter, workload, provider))
    if provider == "openai":
        return _OpenAIClient(client, _Ctx(reporter, workload, provider))
    raise ValueError(
        f"could not detect provider for {type(client)!r}; pass provider='anthropic' "
        "or provider='openai'"
    )
