from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import BaselineProfile, Workload
from app.schemas.auth import CurrentUser
from app.schemas.workloads import BaselineOut, WorkloadOut, WorkloadUpdate

router = APIRouter(tags=["workloads"])


@router.get("/workloads", response_model=list[WorkloadOut])
def list_workloads(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[Workload]:
    return list(db.scalars(select(Workload).order_by(Workload.name)).all())


@router.get("/workloads/{workload_id}/baselines", response_model=list[BaselineOut])
def workload_baselines(
    workload_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[BaselineProfile]:
    """The seasonal baselines learned for a workload, for the "typical by hour"
    view and its coverage badge. Returns every (metric, hour) the refresh has
    populated; an empty list means none are trusted yet (still learning, or the
    seasonal path is disabled), and the detector is on its rolling-window
    fallback. Tenant-scoped: a workload in another account 404s under RLS."""
    if db.get(Workload, workload_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return list(
        db.scalars(
            select(BaselineProfile)
            .where(BaselineProfile.workload_id == workload_id)
            .order_by(BaselineProfile.metric, BaselineProfile.bucket)
        ).all()
    )


@router.patch("/workloads/{workload_id}", response_model=WorkloadOut)
def update_workload(
    workload_id: int,
    body: WorkloadUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> Workload:
    """Publish or unpublish a workload on the public status page (admin only)."""
    workload = db.get(Workload, workload_id)
    if workload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    workload.public = body.public
    db.commit()
    db.refresh(workload)
    return workload
