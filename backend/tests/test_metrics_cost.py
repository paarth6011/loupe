def _post(client, headers, **body):
    base = {"workload": "wl", "latency_ms": 100, "status": "ok"}
    base.update(body)
    return client.post("/metrics", json=base, headers=headers)


def test_ingest_auto_computes_cost(client, auth_headers):
    """When the client omits cost_usd, the server estimates it from pricing."""
    resp = _post(
        client,
        auth_headers,
        workload="claude-bot",
        model="claude-haiku-4-5",
        provider="anthropic",
        input_tokens=420,
        output_tokens=85,
    )
    assert resp.status_code == 201
    assert resp.json()["sample"]["cost_usd"] == 0.000845  # 420*$1/M + 85*$5/M


def test_client_supplied_cost_is_respected(client, auth_headers):
    resp = _post(
        client,
        auth_headers,
        workload="x",
        model="claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=1000,
        cost_usd=0.123,
    )
    assert resp.json()["sample"]["cost_usd"] == 0.123


def test_cost_breakdown_by_model_and_workload(client, auth_headers):
    _post(
        client,
        auth_headers,
        workload="bot-a",
        model="gpt-4o",
        provider="openai",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    _post(
        client,
        auth_headers,
        workload="bot-b",
        model="claude-haiku-4-5",
        provider="anthropic",
        input_tokens=0,
        output_tokens=1_000_000,
    )

    out = client.get("/metrics/cost?window=24h", headers=auth_headers).json()
    assert out["total_cost_usd"] == round(2.5 + 5.0, 6)  # gpt-4o in + haiku out
    models = {m["model"]: m for m in out["by_model"]}
    assert models["gpt-4o"]["cost_usd"] == 2.5
    assert models["claude-haiku-4-5"]["cost_usd"] == 5.0
    # by_workload is sorted by spend, highest first
    assert out["by_workload"][0]["cost_usd"] >= out["by_workload"][-1]["cost_usd"]


def test_cost_invalid_window(client, auth_headers):
    assert (
        client.get("/metrics/cost?window=nope", headers=auth_headers).status_code == 422
    )


def test_cost_requires_auth(client):
    assert client.get("/metrics/cost?window=24h").status_code == 401
