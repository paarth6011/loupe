from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.alerts import AlertOut


class MetricIngest(BaseModel):
    workload: str = Field(min_length=1, max_length=255)  # name; auto-created if new
    latency_ms: int = Field(ge=0)
    status: Literal["ok", "error"]
    tokens: int | None = Field(default=None, ge=0)  # legacy total
    ts: datetime | None = None  # defaults to server time when omitted

    # LLM-workload fields (all optional).
    model: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=64)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    operation: str | None = Field(default=None, max_length=32)
    error_type: str | None = Field(default=None, max_length=32)


class MetricSampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workload_id: int
    ts: datetime
    latency_ms: int
    status: str
    tokens: int | None
    model: str | None
    provider: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    operation: str | None
    error_type: str | None


class MetricIngestResponse(BaseModel):
    sample: MetricSampleOut
    triggered_alerts: list[AlertOut]
    resolved_alerts: list[AlertOut] = []


class MetricsSummary(BaseModel):
    workload_id: int
    window: str
    request_count: int
    error_count: int
    error_rate: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    # LLM cost/token rollups (default 0 keeps older cached payloads valid).
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


class CostByModel(BaseModel):
    model: str
    provider: str | None
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostByWorkload(BaseModel):
    workload_id: int
    workload: str
    requests: int
    cost_usd: float


class CostSummary(BaseModel):
    window: str
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    by_model: list[CostByModel]
    by_workload: list[CostByWorkload]


class TimeseriesPoint(BaseModel):
    bucket_start: datetime
    request_count: int
    error_rate: float
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    # LLM throughput/spend per bucket (default 0 so HTTP-only buckets are valid).
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class MetricsTimeseries(BaseModel):
    workload_id: int
    window: str
    bucket: str
    points: list[TimeseriesPoint]
