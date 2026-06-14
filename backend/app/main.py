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

# Fail closed: never run a production deployment on a fatal misconfiguration —
# insecure dev secrets, multi-tenant auth without the restricted DB role (which
# would silently disable row-level security), or wildcard CORS. In dev we only
# warn about the insecure secrets so the local stack stays frictionless.
if _settings.is_production():
    _blockers = _settings.production_blockers()
    if _blockers:
        raise RuntimeError(
            "Refusing to start in production: "
            + "; ".join(_blockers)
            + ". Set ENVIRONMENT=dev to override for local development."
        )
else:
    _insecure = _settings.insecure_defaults()
    if _insecure:
        logging.getLogger("uvicorn.error").warning(
            "Running with insecure development defaults (%s). "
            "Do NOT use these in production.",
            "; ".join(_insecure),
        )

app = FastAPI(title="Loupe API", version="0.1.0")

# Allowed origins come from config (localhost in dev; the frontend URL in prod).
# A wildcard origin is refused at boot in production (see production_blockers).
_origins = _settings.cors_origin_list()
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
