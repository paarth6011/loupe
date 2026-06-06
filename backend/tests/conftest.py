from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import InMemoryCache, get_cache
from app.database import Base, get_db
from app.main import app
from app import models as _models  # noqa: F401  (register tables on Base.metadata)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """In-memory SQLite session with a fresh schema per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient whose get_db dependency uses the in-memory session."""

    def override_get_db() -> Iterator[Session]:
        yield db_session

    cache = InMemoryCache()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cache] = lambda: cache
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
