#!/usr/bin/env bash
#
# Orchestrate a full-stack end-to-end run: start the Django backend, seed the
# deterministic E2E dataset, then run the Playwright suite (which starts the
# Next.js frontend itself via its webServer config). The backend is stopped on
# exit no matter how the run ends.
#
# Assumes infra (Postgres + Redis) is already up and migrated -- the `e2e-full`
# make target does `infra-up migrate` before invoking this script.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
PY="$BACKEND_DIR/.venv/bin/python"
export DJANGO_SETTINGS_MODULE="config.settings.dev"

BACKEND_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo ">> stopping backend (pid $BACKEND_PID)"
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo ">> starting backend on 127.0.0.1:8000"
( cd "$BACKEND_DIR" && "$PY" manage.py runserver 127.0.0.1:8000 --noreload ) &
BACKEND_PID=$!

echo ">> waiting for backend health"
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null http://127.0.0.1:8000/api/v1/health/; then
    echo ">> backend is up"
    break
  fi
  sleep 0.5
done

echo ">> seeding E2E dataset"
( cd "$BACKEND_DIR" && "$PY" manage.py seed_e2e )

echo ">> running Playwright suite"
( cd "$FRONTEND_DIR" && npm run e2e -- "$@" )
