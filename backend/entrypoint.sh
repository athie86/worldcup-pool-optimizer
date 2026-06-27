#!/bin/sh
# Container entrypoint: bring the database schema up to date, then serve.
#
# Running `alembic upgrade head` on every start means schema changes ship
# automatically on deploy — no manual migration step. It is idempotent: if the
# database is already current it is a no-op, and migrations are written to be
# safe against databases first created by the app's create_all startup path.
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
