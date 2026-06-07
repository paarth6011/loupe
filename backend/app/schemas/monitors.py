from pydantic import BaseModel, Field


class MonitorOut(BaseModel):
    rule: str
    label: str
    unit: str
    detector: str
    integer: bool  # whether the threshold is a whole number (for UI input step)
    enabled: bool
    threshold: float | None  # the per-workload override, or null if using default
    default_threshold: float  # the global default from Settings
    effective_threshold: float  # override if set, else default


class MonitorUpdate(BaseModel):
    # Both optional. Only fields actually present in the request body are applied
    # (tracked via model_fields_set), so threshold can be sent as null to clear
    # an override and fall back to the global default.
    enabled: bool | None = None
    threshold: float | None = Field(default=None, ge=0)
