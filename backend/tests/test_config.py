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


def test_environment_defaults_to_production():
    # Secure by default: the declared default must be production so a deployment
    # that never sets ENVIRONMENT fails closed (refuses insecure secrets, hides
    # /auth/dev-login) instead of silently running in permissive dev mode.
    assert Settings.model_fields["environment"].default == "prod"
