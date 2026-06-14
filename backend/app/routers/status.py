from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db, set_current_account
from app.deps import DEFAULT_ACCOUNT_NAME
from app.models import Account, Workload
from app.schemas.status import StatusPageOut
from app.status import build_status_page

router = APIRouter(tags=["status"])


@router.get("/status", response_model=StatusPageOut)
def public_status(db: Session = Depends(get_db)) -> StatusPageOut:
    """Public, no-auth status page for the single-tenant (self-host) deployment.

    This endpoint has no caller identity, so it is scoped explicitly to the
    default account — both by pinning row-level security and by an ``account_id``
    filter. That makes it impossible to commingle tenants on a multi-tenant
    deploy: without the scope it would otherwise leak every tenant's public
    workloads onto one page (if the app ran with RLS bypassed). Per-tenant public
    status pages (a /status/{slug} with its own account) would be a follow-up.

    Only workloads explicitly marked public are exposed, and only their health —
    never cost, tokens, or alert detail. Operators opt a workload in from the
    dashboard.
    """
    account_id = db.scalar(
        select(Account.id).where(Account.name == DEFAULT_ACCOUNT_NAME)
    )
    if account_id is None:
        return build_status_page(db, [])
    set_current_account(db, account_id)
    workloads = list(
        db.scalars(
            select(Workload)
            .where(Workload.public.is_(True), Workload.account_id == account_id)
            .order_by(Workload.name)
        ).all()
    )
    return build_status_page(db, workloads)
