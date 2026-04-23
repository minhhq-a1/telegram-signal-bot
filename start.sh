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

# Run migration (idempotent)
echo "Running database migration..."
python3 -c "
import os
import psycopg
# Dùng driver postgresql:// cơ bản cho migration script (psycopg direct)
url = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
try:
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            sql = open('migrations/001_init.sql').read()
            cur.execute(sql)
        conn.commit()
    print('✅ Migration: OK')
except Exception as e:
    print(f'❌ Migration Failed: {e}')
    exit(1)
"

# Start the server
PORT="${PORT:-8080}"
echo "🚀 Starting uvicorn on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'