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


class BaselineOut(BaseModel):
    """One learned seasonal baseline: a workload's typical value for a metric in
    a given UTC hour-of-day. Powers the "typical latency by hour" view and its
    coverage badge (how many of the 24 hours have been learned)."""

    model_config = ConfigDict(from_attributes=True)

    metric: str  # "latency" | "cost"
    bucket: int  # UTC hour-of-day, 0–23
    center: float  # the learned median
    scale: float  # robust spread (MAD×1.4826)
    n: int  # samples behind this bucket
