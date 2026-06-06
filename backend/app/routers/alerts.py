from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
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
