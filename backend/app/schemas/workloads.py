from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    public: bool


class WorkloadUpdate(BaseModel):
    # Publish/unpublish a workload on the public status page.
    public: bool
