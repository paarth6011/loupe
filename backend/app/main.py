from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import alerts, auth, health, metrics, workloads

app = FastAPI(title="Cloud Ops Dashboard API", version="0.1.0")

# Frontend dev server (Vite) runs on 5173 locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(metrics.router)
app.include_router(workloads.router)
app.include_router(alerts.router)
