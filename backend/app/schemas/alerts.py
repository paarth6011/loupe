from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workload_id: int
    rule: str
    message: str
    severity: str
    summary: str | None
    triggered_at: datetime
    resolved_at: datetime | None
