from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apikeys import verify_ingest_key
from app.auth import decode_supabase_token, decode_token
from app.database import get_db
from app.models import Account, User
from app.schemas.auth import CurrentUser

# auto_error=False so missing credentials yield our own 401 (not a 403).
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)

# The single-tenant self-host deploy lives in this account (created by migration
# 0010). The admin login resolves here.
DEFAULT_ACCOUNT_NAME = "default"


def _provision_supabase_user(db: Session, claims: dict) -> User | None:
    """Map a verified Supabase token to a Loupe user, creating the account and
    user just-in-time on first sight. Returns None if the token has no subject.

    accounts/users are *not* under row-level security (they are the
    auth-bootstrap tables — see docs/multi-tenancy.md), so this lookup/insert
    runs before any tenant is pinned, which is exactly what establishes it.
    """
    sub = claims.get("sub")
    if not sub:
        return None
    user = db.scalar(select(User).where(User.supabase_user_id == sub))
    if user is not None:
        return user
    # First authenticated request from this Supabase user: stand up their tenant.
    email = claims.get("email")
    account = Account(name=email or sub)
    db.add(account)
    db.flush()  # assign account.id before linking the user
    user = User(
        account_id=account.id,
        supabase_user_id=sub,
        email=email,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _default_account_id(db: Session) -> int | None:
    return db.scalar(
        select(Account.id).where(Account.name == DEFAULT_ACCOUNT_NAME)
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise _UNAUTHORIZED
    token = credentials.credentials

    # Multi-tenant path: a Supabase end-user token resolves to that user's tenant.
    claims = decode_supabase_token(token)
    if claims is not None:
        user = _provision_supabase_user(db, claims)
        if user is not None:
            return CurrentUser(
                account_id=user.account_id,
                user_id=user.id,
                email=user.email,
                username=user.email,
            )

    # Self-host path: the admin JWT maps to the single default account.
    username = decode_token(token)
    if username is not None:
        account_id = _default_account_id(db)
        if account_id is not None:
            return CurrentUser(account_id=account_id, username=username)

    raise _UNAUTHORIZED


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
