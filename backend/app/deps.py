from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apikeys import verify_ingest_key
from app.auth import decode_supabase_token, decode_token
from app.database import get_db, set_current_account
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


def _find_loupe_user(db: Session, sub: str, email: str | None) -> User | None:
    """Find the existing Loupe user for a Supabase identity, read-only.

    Matches on the stable Supabase id first; failing that, on email. The email
    fallback catches the *same person under a new Supabase id* — e.g. they
    deleted and recreated their Supabase account, minting a fresh ``sub`` for an
    unchanged, already-confirmed email. Returns None if neither matches.
    """
    user = db.scalar(select(User).where(User.supabase_user_id == sub))
    if user is not None:
        return user
    if email is not None:
        return db.scalar(select(User).where(User.email == email))
    return None


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
    email = claims.get("email")

    user = _find_loupe_user(db, sub, email)
    if user is not None:
        if user.supabase_user_id != sub:
            # Found by email, not id: the same person came back under a new
            # Supabase identity (their account was deleted and recreated). Re-link
            # to the new ``sub`` instead of inserting a second row — users.email is
            # UNIQUE, so an insert would 500 *every* authenticated request (it runs
            # through get_current_user). The email is Supabase-verified, so this is
            # the same human keeping their existing account and data.
            user.supabase_user_id = sub
            db.commit()
            db.refresh(user)
        return user

    # First time we've seen this person: stand up their tenant. Guard the insert
    # against a race — the dashboard fires several authed requests in parallel, so
    # two "first" requests can reach here at once; whichever loses the unique
    # constraint rolls back and re-reads the winner's row.
    try:
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
    except IntegrityError:
        db.rollback()
        return _find_loupe_user(db, sub, email)


def _default_account_id(db: Session) -> int | None:
    return db.scalar(select(Account.id).where(Account.name == DEFAULT_ACCOUNT_NAME))


def _resolve_bearer(db: Session, token: str) -> CurrentUser | None:
    """Resolve a bearer token to a tenant-scoped principal, or None.

    Tries the Supabase end-user token first (the multi-tenant path, provisioning
    the account/user just-in-time), then falls back to the self-host admin JWT,
    which maps to the single ``default`` account. Does not pin the session — the
    caller decides whether this request should be tenant-scoped.
    """
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

    username = decode_token(token)
    if username is not None:
        account_id = _default_account_id(db)
        if account_id is not None:
            return CurrentUser(account_id=account_id, username=username)

    return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise _UNAUTHORIZED
    user = _resolve_bearer(db, credentials.credentials)
    if user is None:
        raise _UNAUTHORIZED
    # Pin the shared request session so row-level security scopes every read to
    # this tenant (FastAPI caches get_db, so the route body gets this same one).
    set_current_account(db, user.account_id)
    return user


def require_ingest_auth(
    x_api_key: str | None = Header(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> int:
    """Authenticate an ingest request and return its tenant's ``account_id``.

    The SDK and external sources use an `X-API-Key` header (revocable, scoped to
    ingestion); the key belongs to one account, which becomes the request's
    tenant. A Supabase end-user token or the self-host admin JWT is also accepted
    so the dashboard and manual posting keep working. The resolved account is
    used to pin the session (RLS) and to stamp `account_id` on ingested rows.
    """
    if x_api_key:
        key = verify_ingest_key(db, x_api_key)
        if key is not None:
            set_current_account(db, key.account_id)
            return key.account_id
        raise _UNAUTHORIZED
    if credentials is not None:
        user = _resolve_bearer(db, credentials.credentials)
        if user is not None:
            set_current_account(db, user.account_id)
            return user.account_id
    raise _UNAUTHORIZED


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Authorize the self-host operator for deployment-wide actions (e.g. data
    retention pruning).

    The admin login maps to the single ``default`` account and carries no
    ``user_id``; provisioned Supabase end users always have one. So a tenant on
    the multi-tenant SaaS calling an operator endpoint is refused with 403 — a
    destructive, cross-tenant action (prune deletes by time across all tenants)
    must never be reachable by an ordinary tenant.
    """
    if user.user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="operator privileges required",
        )
    return user
