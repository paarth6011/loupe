from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StreamTicketResponse(BaseModel):
    """A short-lived, read-only credential for opening the SSE stream."""

    ticket: str


class CurrentUser(BaseModel):
    # Every authenticated request resolves to exactly one tenant; `account_id`
    # is what scopes the request (and pins row-level security).
    account_id: int
    # The authenticated principal. `user_id`/`email` are set for Supabase end
    # users; `username` is kept for the self-host admin login.
    user_id: int | None = None
    email: str | None = None
    username: str | None = None
