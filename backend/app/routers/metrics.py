from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerting import evaluate_thresholds
from app.config import Settings, get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import MetricSample, Workload
from app.schemas.auth import CurrentUser
from app.schemas.metrics import MetricIngest, MetricIngestResponse

router = APIRouter(tags=["metrics"])


def _get_or_create_workload(db: Session, name: str) -> Workload:
    workload = db.scalars(select(Workload).where(Workload.name == name)).first()
    if workload is not None:
        return workload
    workload = Workload(name=name)
    db.add(workload)
    db.flush()
    return workload


@router.post(
    "/metrics", response_model=MetricIngestResponse, status_code=status.HTTP_201_CREATED
)
def ingest_metric(
    body: MetricIngest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: CurrentUser = Depends(get_current_user),
) -> MetricIngestResponse:
    workload = _get_or_create_workload(db, body.workload)

    sample = MetricSample(
        workload_id=workload.id,
        latency_ms=body.latency_ms,
        status=body.status,
        tokens=body.tokens,
    )
    if body.ts is not None:
        sample.ts = body.ts
    db.add(sample)
    db.flush()  # assign id + server-default ts and make it visible to threshold queries

    triggered = evaluate_thresholds(db, sample, settings)

    db.commit()
    db.refresh(sample)
    return MetricIngestResponse(sample=sample, triggered_alerts=triggered)
