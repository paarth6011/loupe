from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import decode_token
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
