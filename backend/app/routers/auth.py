from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import authenticate, create_access_token, create_stream_ticket
from app.cache import Cache, get_cache
from app.config import Settings, get_settings
from app.deps import get_current_user
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    StreamTicketResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Brute-force protection: after this many *failed* attempts from one client IP
# within the window, further attempts are refused with 429 until the window
# rolls off. Successful logins reset the counter, so a legitimate user fumbling
# their password is never locked out for long. Fail-open if the cache is down.
_LOGIN_MAX_FAILURES = 10
_LOGIN_WINDOW_SECONDS = 300


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    cache: Cache = Depends(get_cache),
) -> TokenResponse:
    key = f"login_fail:{_client_ip(request)}"
    if int(cache.get(key) or 0) >= _LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts; try again later.",
        )
    if not authenticate(body.username, body.password):
        cache.incr(key, _LOGIN_WINDOW_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    cache.delete(key)  # reset the failure counter on success
    return TokenResponse(access_token=create_access_token(body.username))


@router.post("/dev-login", response_model=TokenResponse)
def dev_login(settings: Settings = Depends(get_settings)) -> TokenResponse:
    """Frictionless local login. In non-production environments only, issue an
    admin token without credentials so the dashboard skips the sign-in screen on
    a developer's machine.

    Refused with 404 in production, where a real login (and a non-default
    password, enforced at boot) is mandatory — so this endpoint effectively does
    not exist on a deployed instance. It is a UX shortcut, not an auth bypass:
    every protected endpoint still requires the resulting token.
    """
    if settings.is_production():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return TokenResponse(access_token=create_access_token(settings.admin_username))


@router.post("/stream-ticket", response_model=StreamTicketResponse)
def stream_ticket(
    user: CurrentUser = Depends(get_current_user),
) -> StreamTicketResponse:
    """Exchange the bearer token for a short-lived, read-only ticket used to open
    the SSE stream. Keeps the full JWT out of the stream URL, and carries the
    viewer's account so the stream stays scoped to their tenant."""
    return StreamTicketResponse(
        ticket=create_stream_ticket(user.username, user.account_id)
    )


@router.get("/me", response_model=CurrentUser)
def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Return the authenticated user; handy for the frontend session check."""
    return user
