from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Workload
from app.schemas.auth import CurrentUser
from app.schemas.workloads import WorkloadOut

router = APIRouter(tags=["workloads"])


@router.get("/workloads", response_model=list[WorkloadOut])
def list_workloads(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[Workload]:
    return list(db.scalars(select(Workload).order_by(Workload.name)).all())
