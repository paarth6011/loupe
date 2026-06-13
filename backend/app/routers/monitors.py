from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Monitor, Workload
from app.rules import RULE_SPEC_BY_NAME, RULE_SPECS, RuleSpec, default_threshold
from app.schemas.auth import CurrentUser
from app.schemas.monitors import MonitorOut, MonitorUpdate

router = APIRouter(tags=["monitors"])


def _to_out(spec: RuleSpec, monitor: Monitor | None, settings: Settings) -> MonitorOut:
    default = default_threshold(spec, settings)
    override = monitor.threshold if monitor is not None else None
    return MonitorOut(
        rule=spec.rule,
        label=spec.label,
        unit=spec.unit,
        detector=spec.detector,
        integer=spec.integer,
        enabled=monitor.enabled if monitor is not None else True,
        threshold=override,
        default_threshold=default,
        effective_threshold=override if override is not None else default,
    )


def _require_workload(db: Session, workload_id: int) -> None:
    if db.get(Workload, workload_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workload not found"
        )


@router.get("/workloads/{workload_id}/monitors", response_model=list[MonitorOut])
def list_monitors(
    workload_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: CurrentUser = Depends(get_current_user),
) -> list[MonitorOut]:
    """Every rule's effective config for a workload (overrides merged on top of
    the global defaults), so the UI can render the full set in one call."""
    _require_workload(db, workload_id)
    rows = {
        m.rule: m
        for m in db.scalars(
            select(Monitor).where(Monitor.workload_id == workload_id)
        ).all()
    }
    return [_to_out(spec, rows.get(spec.rule), settings) for spec in RULE_SPECS]


@router.put("/workloads/{workload_id}/monitors/{rule}", response_model=MonitorOut)
def update_monitor(
    workload_id: int,
    rule: str,
    body: MonitorUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: CurrentUser = Depends(get_current_user),
) -> MonitorOut:
    """Enable/disable a rule or override its threshold for one workload.

    Upserts the monitor row. Only fields present in the body are applied; send
    ``threshold: null`` to drop an override and fall back to the default.
    """
    _require_workload(db, workload_id)
    spec = RULE_SPEC_BY_NAME.get(rule)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown rule '{rule}'"
        )

    monitor = db.scalars(
        select(Monitor).where(Monitor.workload_id == workload_id, Monitor.rule == rule)
    ).first()
    if monitor is None:
        # The workload was just resolved under this tenant's RLS pin, so its
        # account is the current user's; stamp it so the monitor is co-tenant.
        monitor = Monitor(
            account_id=current_user.account_id,
            workload_id=workload_id,
            rule=rule,
            enabled=True,
        )
        db.add(monitor)

    fields = body.model_fields_set
    if "enabled" in fields and body.enabled is not None:
        monitor.enabled = body.enabled
    if "threshold" in fields:
        monitor.threshold = body.threshold

    db.commit()
    db.refresh(monitor)
    return _to_out(spec, monitor, settings)
