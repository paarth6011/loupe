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
    username: str
