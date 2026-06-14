from app.config import (
    INSECURE_ADMIN_PASSWORD,
    INSECURE_JWT_SECRET,
    Settings,
)


def test_insecure_defaults_flagged():
    s = Settings(jwt_secret=INSECURE_JWT_SECRET, admin_password=INSECURE_ADMIN_PASSWORD)
    assert len(s.insecure_defaults()) == 2


def test_secure_values_not_flagged():
    s = Settings(jwt_secret="a-long-random-secret-value", admin_password="s3cret-pw!")
    assert s.insecure_defaults() == []


def test_is_production_detection():
    assert Settings(environment="prod").is_production() is True
    assert Settings(environment="PRODUCTION").is_production() is True
    assert Settings(environment="dev").is_production() is False


def test_runtime_url_is_owner_when_no_app_password():
    # Without app_db_password, the app serves on the owner connection (dev/tests/
    # single-tenant) — migrations and runtime share one URL, as before.
    s = Settings(database_url="postgresql+psycopg://owner:pw@db:5432/loupe")
    assert s.runtime_database_url() == s.database_url


def test_runtime_url_swaps_to_restricted_role_when_app_password_set():
    # With app_db_password set, runtime serves as the restricted role on the same
    # host/db (so RLS binds); migrations still use database_url (the owner).
    s = Settings(
        database_url="postgresql+psycopg://owner:pw@db:5432/loupe",
        app_db_user="loupe_app",
        app_db_password="secret",
    )
    url = s.runtime_database_url()
    assert url.startswith("postgresql+psycopg://")  # same driver
    assert "loupe_app:secret@db:5432/loupe" in url  # restricted creds, same target
    assert "owner" not in url


def test_environment_defaults_to_production():
    # Secure by default: the declared default must be production so a deployment
    # that never sets ENVIRONMENT fails closed (refuses insecure secrets, hides
    # /auth/dev-login) instead of silently running in permissive dev mode.
    assert Settings.model_fields["environment"].default == "prod"


def _secure_base(**overrides) -> Settings:
    """A production-safe Settings, overridable per test."""
    base = dict(jwt_secret="a-long-random-secret-value", admin_password="s3cret-pw!")
    base.update(overrides)
    return Settings(**base)


def test_multitenant_enabled_detection():
    assert _secure_base().multitenant_enabled() is False
    assert _secure_base(supabase_url="https://x.supabase.co").multitenant_enabled()
    assert _secure_base(supabase_jwt_secret="legacy-hs256").multitenant_enabled()


def test_blocker_multitenant_without_restricted_role():
    # Supabase on but no APP_DB_PASSWORD => app would bypass RLS. Must block boot.
    s = _secure_base(supabase_url="https://proj.supabase.co", app_db_password="")
    blockers = s.production_blockers()
    assert any("APP_DB_PASSWORD" in b for b in blockers)


def test_no_blocker_multitenant_with_restricted_role():
    s = _secure_base(supabase_url="https://proj.supabase.co", app_db_password="pw")
    assert s.production_blockers() == []


def test_no_blocker_single_tenant_without_restricted_role():
    # Self-host single-tenant (no Supabase) doesn't need the restricted role.
    assert _secure_base(app_db_password="").production_blockers() == []


def test_blocker_wildcard_cors():
    s = _secure_base(cors_origins="https://app.example.com, *")
    assert any("CORS_ORIGINS" in b for b in s.production_blockers())


def test_production_blockers_includes_insecure_defaults():
    s = Settings(jwt_secret=INSECURE_JWT_SECRET, admin_password=INSECURE_ADMIN_PASSWORD)
    assert len(s.production_blockers()) == 2
