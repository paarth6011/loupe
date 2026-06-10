from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Alert
from app.schemas.alerts import AlertOut
from app.schemas.auth import CurrentUser

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    workload_id: int | None = None,
    resolved: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[Alert]:
    stmt = select(Alert)
    if workload_id is not None:
        stmt = stmt.where(Alert.workload_id == workload_id)
    if resolved is True:
        stmt = stmt.where(Alert.resolved_at.is_not(None))
    elif resolved is False:
        stmt = stmt.where(Alert.resolved_at.is_(None))
    stmt = stmt.order_by(Alert.triggered_at.desc(), Alert.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Alert:
    """Manually resolve an open alert.

    Loupe normally resolves an alert when a later ingest sees the rule recover,
    but a workload that simply goes quiet can leave a stale alert open forever
    (nothing re-evaluates it). This lets an operator clear it by hand.
    Idempotent: resolving an already-resolved alert is a no-op.
    """
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if alert.resolved_at is None:
        alert.resolved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/reopen", response_model=AlertOut)
def reopen_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Alert:
    """Reopen a resolved alert — backs the "Undo" on a manual resolve.

    Idempotent for an already-open alert. Can legitimately fail: the partial
    unique index allows only one open alert per (workload, rule), so if a fresh
    alert for the same rule opened in the meantime, reopening this one would
    duplicate it — we surface that as a 409 rather than corrupt the invariant.
    """
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if alert.resolved_at is not None:
        alert.resolved_at = None
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A newer alert for this rule is already open.",
            )
        db.refresh(alert)
    return alert
