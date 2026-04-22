#!/bin/bash
set -e

echo "=== Signal Bot V1 — Starting ==="

# Railway injects DATABASE_URL as postgresql:// (psycopg2 format)
# We need postgresql+psycopg:// (psycopg3 format)
if [ -n "$DATABASE_URL" ]; then
    export DATABASE_URL="${DATABASE_URL/postgresql:\/\//postgresql+psycopg://}"
    export DATABASE_URL="${DATABASE_URL/postgres:\/\//postgresql+psycopg://}"
    echo "DATABASE_URL driver normalized."
fi

# Run migration (idempotent — IF NOT EXISTS, safe to re-run)
echo "Running database migration..."
python3 -c "
import os
import psycopg
url = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        sql = open('migrations/001_init.sql').read()
        cur.execute(sql)
    conn.commit()
print('Migration: OK')
"

# Start the server — use PORT from Railway or fallback to 8080
PORT="${PORT:-8080}"
echo "Starting uvicorn on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"