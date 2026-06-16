from fastapi import APIRouter, Depends
from sqlalchemy.orm import sessionmaker

from app.baselines import refresh_baselines
from app.config import Settings, get_settings
from app.database import get_session_factory
from app.deps import require_admin
from app.retention import prune_old_data
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/prune")
def prune(
    days: int | None = None,
    settings: Settings = Depends(get_settings),
    session_factory: sessionmaker = Depends(get_session_factory),
    _: CurrentUser = Depends(require_admin),
) -> dict:
    """Delete data older than `days` (defaults to RETENTION_DAYS). Operator-only.

    Prune is a deployment-wide, destructive action (it deletes by timestamp, not
    per tenant), so it is gated to the self-host operator via require_admin — an
    ordinary multi-tenant end user is refused with 403. Runs the same routine as
    the background sweep, for on-demand cleanup.
    """
    effective = days if days is not None else settings.retention_days
    result = prune_old_data(session_factory, effective)
    return {
        "days": effective,
        "samples_deleted": result.samples_deleted,
        "alerts_deleted": result.alerts_deleted,
    }


@router.post("/refresh-baselines")
def refresh_baselines_now(
    settings: Settings = Depends(get_settings),
    session_factory: sessionmaker = Depends(get_session_factory),
    _: CurrentUser = Depends(require_admin),
) -> dict:
    """Recompute the seasonal anomaly baselines for every tenant on demand.

    Runs the same routine as the background sweep — useful right after enabling
    the feature, or after backfilling history, so the detector starts using the
    seasonal baselines without waiting for the next scheduled refresh. Operator-
    only: it scans across tenants, like prune.
    """
    result = refresh_baselines(session_factory, settings)
    return {
        "accounts": result.accounts,
        "profiles_written": result.profiles_written,
    }
