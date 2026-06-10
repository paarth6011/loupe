from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Workload
from app.schemas.status import StatusPageOut
from app.status import build_status_page

router = APIRouter(tags=["status"])


@router.get("/status", response_model=StatusPageOut)
def public_status(db: Session = Depends(get_db)) -> StatusPageOut:
    """Public, no-auth status page. Only workloads explicitly marked public are
    exposed, and only their health is shown — never cost, tokens, or alert
    detail. Operators opt a workload in from the dashboard."""
    workloads = list(
        db.scalars(
            select(Workload).where(Workload.public.is_(True)).order_by(Workload.name)
        ).all()
    )
    return build_status_page(db, workloads)
