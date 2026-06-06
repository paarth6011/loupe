from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.alerts import AlertOut


class MetricIngest(BaseModel):
    workload: str = Field(min_length=1, max_length=255)  # name; auto-created if new
    latency_ms: int = Field(ge=0)
    status: Literal["ok", "error"]
    tokens: int | None = Field(default=None, ge=0)
    ts: datetime | None = None  # defaults to server time when omitted


class MetricSampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workload_id: int
    ts: datetime
    latency_ms: int
    status: str
    tokens: int | None


class MetricIngestResponse(BaseModel):
    sample: MetricSampleOut
    triggered_alerts: list[AlertOut]
