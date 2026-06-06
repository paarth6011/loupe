from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import alerts, auth, health, metrics, workloads

app = FastAPI(title="Cloud Ops Dashboard API", version="0.1.0")

# Allowed origins come from config (localhost in dev; the frontend URL in prod).
_origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
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
