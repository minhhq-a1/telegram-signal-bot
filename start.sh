#!/bin/bash
set -e

echo "=== Signal Bot V1 — Starting ==="

# Kiểm tra sự tồn tại của DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL is missing!"
    echo "Please go to Railway Dashboard -> Variables and add DATABASE_URL (reference from your Postgres service)."
    exit 1
fi

# Railway injects DATABASE_URL as postgresql:// (psycopg2 format)
# We need postgresql+psycopg:// (psycopg3 format)
export DATABASE_URL="${DATABASE_URL/postgresql:\/\//postgresql+psycopg://}"
export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql+psycopg://}"
echo "✅ DATABASE_URL driver normalized."

# Run versioned raw-SQL migrations (idempotent)
echo "Running database migrations..."
python3 scripts/db/migrate.py apply

# Start the server
PORT="${PORT:-8080}"
# FORWARDED_ALLOW_IPS defaults to '*' because Railway routes all traffic through
# a single trusted reverse-proxy layer — the app never receives a direct public
# connection. If the deployment topology changes, set this env var explicitly.
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"
echo "🚀 Starting uvicorn on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips="$FORWARDED_ALLOW_IPS"