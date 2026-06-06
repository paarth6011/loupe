from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_settings = get_settings()

# The single-role MVP admin password is supplied as plaintext via env; hash it
# once at import so credential checks go through bcrypt verification.
_ADMIN_PASSWORD_HASH = pwd_context.hash(_settings.admin_password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate(username: str, password: str) -> bool:
    """Validate credentials against the configured single admin user."""
    if username != _settings.admin_username:
        return False
    return verify_password(password, _ADMIN_PASSWORD_HASH)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=_settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_token(token: str) -> str | None:
    """Return the token subject (username) if valid, else None."""
    try:
        payload = jwt.decode(
            token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm]
        )
    except JWTError:
        return None
    return payload.get("sub")
