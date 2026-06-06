from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no DB dependency."""
    return {"status": "ok"}
