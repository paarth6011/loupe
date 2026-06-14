import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.retention import start_retention_worker
from app.routers import (
    admin,
    alerts,
    apikeys,
    auth,
    events,
    health,
    metrics,
    monitors,
    notifications,
    status,
    workloads,
)

_settings = get_settings()

# Fail closed: never run a production deployment on the insecure dev defaults.
_insecure = _settings.insecure_defaults()
if _insecure:
    message = "; ".join(_insecure)
    if _settings.is_production():
        raise RuntimeError(
            f"Refusing to start in production with insecure defaults: {message}. "
            "Set ENVIRONMENT=dev to override, or provide JWT_SECRET / ADMIN_PASSWORD."
        )
    logging.getLogger("uvicorn.error").warning(
        "Running with insecure development defaults (%s). "
        "Do NOT use these in production.",
        message,
    )

app = FastAPI(title="Loupe API", version="0.1.0")

# Allowed origins come from config (localhost in dev; the frontend URL in prod).
_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(metrics.router)
app.include_router(workloads.router)
app.include_router(alerts.router)
app.include_router(monitors.router)
app.include_router(apikeys.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(events.router)
app.include_router(status.router)

# Background data retention (no-op unless RETENTION_DAYS > 0).
start_retention_worker(
    SessionLocal, _settings.retention_days, _settings.retention_sweep_hours
)
