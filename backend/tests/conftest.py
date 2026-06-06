from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import InMemoryCache, get_cache
from app.database import Base, get_db, get_session_factory
from app.main import app
from app.summarizer import AlertContext, get_summarizer
from app import models as _models  # noqa: F401  (register tables on Base.metadata)


class FakeSummarizer:
    """Deterministic summarizer used in tests (no real API calls)."""

    def summarize(self, ctx: AlertContext) -> str:
        return f"[summary] {ctx.workload_name}/{ctx.rule}"


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """One in-memory SQLite engine per test (shared by request + background sessions)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    TestSession = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine: Engine, db_session: Session) -> Iterator[TestClient]:
    """TestClient wired to the in-memory engine, an InMemoryCache, and a fake
    summarizer; background tasks use a session factory on the same engine."""
    test_session_factory = sessionmaker(
        bind=db_engine, autoflush=False, autocommit=False
    )

    def override_get_db() -> Iterator[Session]:
        yield db_session

    cache = InMemoryCache()
    fake_summarizer = FakeSummarizer()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    app.dependency_overrides[get_summarizer] = lambda: fake_summarizer
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
