import os

# The app now defaults to ENVIRONMENT=prod and refuses to import under the
# insecure defaults the suite relies on (admin/admin, placeholder JWT secret).
# Declare the test run as dev *before* importing anything from `app`. setdefault
# lets CI override it explicitly if it wants.
os.environ.setdefault("ENVIRONMENT", "dev")

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  (register tables on Base.metadata)
from app.cache import InMemoryCache, get_cache
from app.database import Base, get_db, get_session_factory
from app.main import app
from app.notifications import AlertEvent
from app.routers.metrics import get_account_notifier
from app.summarizer import AlertContext, get_summarizer


class FakeSummarizer:
    """Deterministic summarizer used in tests (no real API calls)."""

    def summarize(self, ctx: AlertContext) -> str:
        return f"[summary] {ctx.workload_name}/{ctx.rule}"


class CapturingNotifier:
    """Records alert events instead of sending them (no real HTTP)."""

    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    def notify(self, event: AlertEvent) -> None:
        self.events.append(event)


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """In-memory SQLite engine per test (shared by request + background sessions)."""
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


# The single tenant every test runs under. Mirrors what migration 0010 does in
# real deployments (it inserts a "default" account), so the admin login and all
# domain rows resolve to it. SQLite has no row-level security, so cross-tenant
# isolation in this suite is exercised by the explicit account_id filters in app
# code; the Postgres RLS proof lives in test_tenant_isolation.py.
DEFAULT_ACCOUNT_NAME = "default"


@pytest.fixture(autouse=True)
def _seed_default_account(db_engine: Engine) -> int:
    """Seed the default tenant into every test DB and return its id.

    Autouse so API-driven tests (which never touch the account directly) still
    have a tenant for the admin login to resolve to.
    """
    from app.models import Account

    TestSession = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        account = Account(name=DEFAULT_ACCOUNT_NAME)
        session.add(account)
        session.commit()
        return account.id
    finally:
        session.close()


@pytest.fixture
def account_id(_seed_default_account: int) -> int:
    """The id of the seeded default tenant, for stamping rows built directly."""
    return _seed_default_account


@pytest.fixture
def notifier() -> CapturingNotifier:
    return CapturingNotifier()


@pytest.fixture
def client(
    db_engine: Engine, db_session: Session, notifier: CapturingNotifier
) -> Iterator[TestClient]:
    """TestClient wired to the in-memory engine, an InMemoryCache, a fake
    summarizer, and a capturing notifier; background tasks use a session factory
    on the same engine."""
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
    app.dependency_overrides[get_account_notifier] = lambda: notifier
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
