#!/bin/sh
# Container entrypoint. Serves on $PORT (Cloud Run sets this; defaults to 8080).
# Migrations run only when RUN_MIGRATIONS=1 so serving instances don't race them
# on autoscale — in production run them as a one-off (Cloud Run Job / exec).
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    alembic upgrade head
fi

# Trust X-Forwarded-* from the front end so request.client.host is the real
# client IP, not the load balancer's. The login throttle keys on that IP, so
# without this every request looks like it comes from one address and the
# throttle is useless (and can be tripped to lock out the real admin).
# FORWARDED_ALLOW_IPS lists the trusted immediate peers; default to localhost
# only, and set it (e.g. to "*") for the platform that actually fronts this —
# the Cloud Run deployment sets it because only Google's front end can reach the
# container.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
