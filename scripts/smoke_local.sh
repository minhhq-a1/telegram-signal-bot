#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_PORT="${APP_PORT:-8080}"
APP_URL="${APP_URL:-http://127.0.0.1:${APP_PORT}}"
HEALTH_URL="${APP_URL}/api/v1/health"
WEBHOOK_URL="${APP_URL}/api/v1/webhooks/tradingview"
TEMP_DIR="$(mktemp -d)"
APP_PID=""

cleanup() {
  if [[ -n "${APP_PID}" ]] && kill -0 "${APP_PID}" 2>/dev/null; then
    kill "${APP_PID}" >/dev/null 2>&1 || true
    wait "${APP_PID}" 2>/dev/null || true
  fi
  rm -rf "${TEMP_DIR}"
}

trap cleanup EXIT

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
}

require_file ".env"
require_file ".venv/bin/python"
require_file "docs/examples/sample_long_5m.json"

echo "[1/6] Starting PostgreSQL via docker compose"
docker compose up -d db >/dev/null

echo "[2/6] Loading TRADINGVIEW_SHARED_SECRET from .env"
TRADINGVIEW_SHARED_SECRET="$(
  python3 - <<'PY'
from pathlib import Path
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("TRADINGVIEW_SHARED_SECRET="):
        print(line.split("=", 1)[1])
        break
PY
)"

if [[ -z "${TRADINGVIEW_SHARED_SECRET}" ]]; then
  echo "TRADINGVIEW_SHARED_SECRET is missing in .env" >&2
  exit 1
fi

echo "[3/6] Preparing valid payload with local secret"
VALID_PAYLOAD_PATH="${TEMP_DIR}/valid_payload.json"
python3 - <<'PY' "docs/examples/sample_long_5m.json" "${VALID_PAYLOAD_PATH}" "${TRADINGVIEW_SHARED_SECRET}"
import json
import sys
src, dst, secret = sys.argv[1], sys.argv[2], sys.argv[3]
payload = json.load(open(src, encoding="utf-8"))
payload["secret"] = secret
json.dump(payload, open(dst, "w", encoding="utf-8"), ensure_ascii=True)
PY

echo "[4/6] Starting API locally on port ${APP_PORT}"
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${APP_PORT}" >"${TEMP_DIR}/uvicorn.log" 2>&1 &
APP_PID="$!"

for _ in {1..30}; do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "API did not become healthy. See ${TEMP_DIR}/uvicorn.log" >&2
  exit 1
fi

echo "[5/6] Running HTTP smoke checks"

run_request() {
  local name="$1"
  local expected_code="$2"
  local body_file="$3"
  local content_type="${4:-application/json}"
  local output_file="${TEMP_DIR}/${name}.json"
  local http_code

  http_code="$(
    curl -sS -o "${output_file}" -w "%{http_code}" \
      -X POST "${WEBHOOK_URL}" \
      -H "Content-Type: ${content_type}" \
      --data-binary "@${body_file}"
  )"

  if [[ "${http_code}" != "${expected_code}" ]]; then
    echo "${name}: expected HTTP ${expected_code}, got ${http_code}" >&2
    cat "${output_file}" >&2 || true
    exit 1
  fi

  echo "${name}: HTTP ${http_code}"
}

run_request "valid" "200" "${VALID_PAYLOAD_PATH}"
run_request "duplicate" "200" "${VALID_PAYLOAD_PATH}"

INVALID_JSON_PATH="${TEMP_DIR}/invalid_json.txt"
printf '%s' '{"signal_id":"broken","signal":"long"' > "${INVALID_JSON_PATH}"
run_request "invalid_json" "400" "${INVALID_JSON_PATH}"

INVALID_SCHEMA_PATH="${TEMP_DIR}/invalid_schema.json"
cat > "${INVALID_SCHEMA_PATH}" <<'EOF'
{"secret":"test","signal":"long","symbol":"BTCUSDT"}
EOF
run_request "invalid_schema" "400" "${INVALID_SCHEMA_PATH}"

python3 - <<'PY' "${TEMP_DIR}"
import json
import sys
from pathlib import Path

temp_dir = Path(sys.argv[1])

valid = json.loads((temp_dir / "valid.json").read_text(encoding="utf-8"))
duplicate = json.loads((temp_dir / "duplicate.json").read_text(encoding="utf-8"))
invalid_json = json.loads((temp_dir / "invalid_json.json").read_text(encoding="utf-8"))
invalid_schema = json.loads((temp_dir / "invalid_schema.json").read_text(encoding="utf-8"))

assert valid["decision"] in {"PASS_MAIN", "PASS_WARNING", "REJECT"}, valid
assert duplicate["decision"] == "DUPLICATE", duplicate
assert "timestamp" in duplicate, duplicate
assert invalid_json["error_code"] == "INVALID_JSON", invalid_json
assert invalid_schema["error_code"] == "INVALID_SCHEMA", invalid_schema

print("[6/6] Smoke assertions passed")
print(f"valid decision: {valid['decision']}")
print(f"duplicate decision: {duplicate['decision']}")
print(f"invalid_json error_code: {invalid_json['error_code']}")
print(f"invalid_schema error_code: {invalid_schema['error_code']}")
PY

echo "Smoke local completed successfully."
