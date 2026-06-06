#!/bin/sh
# Container entrypoint. Serves on $PORT (Cloud Run sets this; defaults to 8080).
# Migrations run only when RUN_MIGRATIONS=1 so serving instances don't race them
# on autoscale — in production run them as a one-off (Cloud Run Job / exec).
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
