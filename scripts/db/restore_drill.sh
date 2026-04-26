#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

SOURCE_DB_URL="${DATABASE_URL:-${INTEGRATION_DATABASE_URL:-}}"
if [[ -z "$SOURCE_DB_URL" ]]; then
  echo "DATABASE_URL or INTEGRATION_DATABASE_URL is required" >&2
  exit 1
fi

python3 - <<'PY' > /tmp/restore_drill_env.sh
import os
from urllib.parse import urlsplit, urlunsplit

raw_url = os.environ.get("DATABASE_URL") or os.environ.get("INTEGRATION_DATABASE_URL")
normalized = raw_url.replace("postgresql+psycopg://", "postgresql://")
parts = urlsplit(normalized)
base = parts.path.rsplit('/', 1)[0]
source_db = "restore_drill_source"
restore_db = "restore_drill_restored"
source_url = urlunsplit((parts.scheme, parts.netloc, f"{base}/{source_db}", parts.query, parts.fragment))
restore_url = urlunsplit((parts.scheme, parts.netloc, f"{base}/{restore_db}", parts.query, parts.fragment))
admin_url = urlunsplit((parts.scheme, parts.netloc, f"{base}/postgres", parts.query, parts.fragment))
for key, value in {
    'SOURCE_URL': source_url,
    'RESTORE_URL': restore_url,
    'ADMIN_URL': admin_url,
    'SOURCE_DB': source_db,
    'RESTORE_DB': restore_db,
}.items():
    print(f'export {key}={value!r}')
PY
source /tmp/restore_drill_env.sh

cleanup() {
  psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${RESTORE_DB}" >/dev/null
  psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${SOURCE_DB}" >/dev/null
  rm -f /tmp/restore_drill_env.sh /tmp/restore_drill.dump
}
trap cleanup EXIT

psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${RESTORE_DB}" >/dev/null
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${SOURCE_DB}" >/dev/null
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${SOURCE_DB}" >/dev/null

python3 scripts/db/migrate.py apply --database-url "$SOURCE_URL"

psql "$SOURCE_URL" -v ON_ERROR_STOP=1 <<'SQL' >/dev/null
INSERT INTO webhook_events (id, source_ip, http_headers, raw_body, auth_status)
VALUES (
  'restore-drill-event-001',
  '127.0.0.1',
  '{"x-test": "restore-drill"}'::jsonb,
  '{"signal_id": "restore-drill-signal-001"}'::jsonb,
  'VALID'
)
ON CONFLICT (id) DO NOTHING;
SQL

pg_dump -Fc -d "$SOURCE_URL" -f /tmp/restore_drill.dump
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${RESTORE_DB}" >/dev/null
pg_restore -d "$RESTORE_URL" /tmp/restore_drill.dump >/dev/null

SCHEMA_COUNT=$(psql "$RESTORE_URL" -At -c "SELECT count(*) FROM schema_migrations")
CONFIG_ROW=$(psql "$RESTORE_URL" -At -c "SELECT config_value->>'migration_strategy' FROM system_configs WHERE config_key = 'db_ops_baseline'")
EVENT_ROW=$(psql "$RESTORE_URL" -At -c "SELECT count(*) FROM webhook_events WHERE id = 'restore-drill-event-001'")

if [[ "$SCHEMA_COUNT" != "2" ]]; then
  echo "Restore drill failed: expected 2 schema_migrations rows, got ${SCHEMA_COUNT}" >&2
  exit 1
fi

if [[ "$CONFIG_ROW" != "raw_sql_versioned" ]]; then
  echo "Restore drill failed: expected db_ops_baseline migration_strategy=raw_sql_versioned, got ${CONFIG_ROW}" >&2
  exit 1
fi

if [[ "$EVENT_ROW" != "1" ]]; then
  echo "Restore drill failed: expected restored webhook_events row, got ${EVENT_ROW}" >&2
  exit 1
fi

echo "restore drill ok"
echo "- source db: ${SOURCE_DB}"
echo "- restored db: ${RESTORE_DB}"
echo "- schema_migrations rows: ${SCHEMA_COUNT}"
echo "- db_ops_baseline.migration_strategy: ${CONFIG_ROW}"
echo "- restored webhook_events rows: ${EVENT_ROW}"
