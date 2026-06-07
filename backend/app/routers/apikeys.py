from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apikeys import generate_key
from app.database import get_db
from app.deps import get_current_user
from app.models import ApiKey
from app.schemas.apikeys import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/apikeys", tags=["apikeys"])


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_apikey(
    body: ApiKeyCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> ApiKeyCreated:
    """Mint a new ingestion key. The plaintext is returned ONCE, here only."""
    raw, prefix, key_hash = generate_key()
    key = ApiKey(name=body.name, prefix=prefix, key_hash=key_hash)
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyCreated(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        key=raw,
    )


@router.get("", response_model=list[ApiKeyOut])
def list_apikeys(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> list[ApiKey]:
    """List active (non-revoked) keys — never the secret, only the prefix."""
    return list(
        db.scalars(
            select(ApiKey)
            .where(ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        ).all()
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_apikey(
    key_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
) -> None:
    """Revoke a key immediately; it stops authenticating on the next request."""
    key = db.get(ApiKey, key_id)
    if key is None or key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="key not found"
        )
    key.revoked_at = datetime.now(timezone.utc)
    db.commit()
