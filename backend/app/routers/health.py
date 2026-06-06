from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cache import Cache, get_cache
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependency checks."""
    return {"status": "ok"}


@router.get("/ready")
def ready(
    db: Session = Depends(get_db),
    cache: Cache = Depends(get_cache),
) -> dict:
    """Readiness probe: verifies the backend can reach Postgres and Redis.

    Returns 503 if any dependency is unreachable so orchestrators (Cloud Run,
    GKE readiness probes) hold traffic until the app can actually serve.
    """
    checks = {"db": False, "redis": False}

    try:
        db.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        checks["db"] = False

    try:
        cache.set("__ready__", "1", 5)
        checks["redis"] = cache.get("__ready__") == "1"
    except Exception:
        checks["redis"] = False

    if not all(checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}
