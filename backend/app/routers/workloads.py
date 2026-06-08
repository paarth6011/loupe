from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Workload
from app.schemas.auth import CurrentUser
from app.schemas.workloads import WorkloadOut, WorkloadUpdate

router = APIRouter(tags=["workloads"])


@router.get("/workloads", response_model=list[WorkloadOut])
def list_workloads(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[Workload]:
    return list(db.scalars(select(Workload).order_by(Workload.name)).all())


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
