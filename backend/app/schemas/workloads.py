from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
