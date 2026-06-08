from datetime import datetime

from pydantic import BaseModel


class StatusComponentOut(BaseModel):
    name: str
    status: str
    uptime_24h: float | None
    latency_p50_ms: float | None
    last_sample_at: datetime | None


class StatusPageOut(BaseModel):
    overall: str
    generated_at: datetime
    components: list[StatusComponentOut]
