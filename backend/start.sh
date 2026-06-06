#!/bin/sh
# Apply migrations, then start the API. Used as the image's default command.
set -e

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
