from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.apikeys import verify_ingest_key
from app.auth import decode_token
from app.database import get_db
from app.schemas.auth import CurrentUser

# auto_error=False so missing credentials yield our own 401 (not a 403).
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise _UNAUTHORIZED
    username = decode_token(credentials.credentials)
    if username is None:
        raise _UNAUTHORIZED
    return CurrentUser(username=username)


def require_ingest_auth(
    x_api_key: str | None = Header(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> None:
    """Authenticate an ingest request via a per-source API key or an admin JWT.

    The SDK and external sources use an `X-API-Key` header (revocable, scoped to
    ingestion). The admin JWT is still accepted so the dashboard and manual
    posting keep working.
    """
    if x_api_key:
        if verify_ingest_key(db, x_api_key) is not None:
            return
        raise _UNAUTHORIZED
    if credentials is not None and decode_token(credentials.credentials) is not None:
        return
    raise _UNAUTHORIZED
