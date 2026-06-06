from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workload_id: int
    rule: str
    message: str
    triggered_at: datetime
    resolved_at: datetime | None
