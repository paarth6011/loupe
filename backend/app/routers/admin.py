from fastapi import APIRouter, Depends
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.database import get_session_factory
from app.deps import get_current_user
from app.retention import prune_old_data
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/prune")
def prune(
    days: int | None = None,
    settings: Settings = Depends(get_settings),
    session_factory: sessionmaker = Depends(get_session_factory),
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    """Delete data older than `days` (defaults to RETENTION_DAYS). Admin-only.

    Runs the same routine as the background sweep, for on-demand cleanup.
    """
    effective = days if days is not None else settings.retention_days
    result = prune_old_data(session_factory, effective)
    return {
        "days": effective,
        "samples_deleted": result.samples_deleted,
        "alerts_deleted": result.alerts_deleted,
    }
