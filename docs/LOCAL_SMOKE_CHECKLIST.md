# Local Smoke Checklist

Mục tiêu: verify nhanh local end-to-end trước khi QA chạy sâu hơn.

## Preconditions

- Đã copy `.env.example` thành `.env`
- Đã điền `TRADINGVIEW_SHARED_SECRET`
- Đã điền Telegram token/chat IDs hợp lệ hoặc chấp nhận test delivery fail
- Đã cài dependencies vào `.venv`
- Đã thay `"secret": "CHANGE_ME"` trong [docs/examples/sample_long_5m.json](/Users/minhhq/Documents/telegram-signal-bot/docs/examples/sample_long_5m.json:1) bằng đúng secret local đang dùng

## Steps

### 1. Start database

```bash
docker compose up -d db
```

### 2. Start API

```bash
./.venv/bin/uvicorn app.main:app --reload --port 8080
```

### 3. Health check

```bash
curl http://localhost:8080/api/v1/health
```

Expected:
- HTTP `200`

### 4. Valid webhook

```bash
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d @docs/examples/sample_long_5m.json
```

Expected:
- HTTP `200`
- response nên có `decision="PASS_MAIN"` với sample payload chuẩn này
- nếu Telegram fail thì business records vẫn phải được lưu

Ghi chú:
- nếu sample payload chuẩn này không ra `PASS_MAIN`, coi như smoke fail và cần kiểm tra lại config/filter logic/sample data

### 5. Duplicate webhook

Gửi lại đúng payload ở bước 4.

Expected:
- HTTP `200`
- response có `decision="DUPLICATE"`
- không tạo thêm `signals`, `signal_filter_results`, `signal_decisions`

### 6. Invalid JSON audit

```bash
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{"signal_id":"broken","signal":"long"'
```

Expected:
- HTTP `400`
- response có `error_code="INVALID_JSON"`
- `webhook_events` vẫn có row audit

### 7. Invalid schema audit

```bash
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{"secret":"test","signal":"long","symbol":"BTCUSDT"}'
```

Expected:
- HTTP `400`
- response có `error_code="INVALID_SCHEMA"`
- `webhook_events` vẫn có row audit

## DB verification

Ví dụ dưới đây áp dụng cho local default trong [.env.example](/Users/minhhq/Documents/telegram-signal-bot/.env.example:1).
Nếu bạn đã đổi `DATABASE_URL`, hãy thay host/user/db tương ứng với môi trường local của bạn.

```bash
PGPASSWORD=postgres psql -h localhost -U postgres -d signal_bot -c "
  SELECT we.auth_status, we.is_valid_json, s.signal_id, sd.decision, tm.delivery_status
  FROM webhook_events we
  LEFT JOIN signals s ON s.webhook_event_id = we.id
  LEFT JOIN signal_decisions sd ON sd.signal_row_id = s.id
  LEFT JOIN telegram_messages tm ON tm.signal_row_id = s.id
  ORDER BY we.received_at DESC
  LIMIT 10;
"
```

Expected:
- thấy đủ audit rows cho valid, duplicate, invalid JSON, invalid schema
- valid signal có linkage `webhook_events -> signals -> signal_decisions`
- nếu Telegram fail thì `telegram_messages.delivery_status='FAILED'`

## V1.3 Feature Verification

### 8. Market context advisory (requires market_context.enabled=true)

```bash
# Insert test market context snapshot
PGPASSWORD=postgres psql -h localhost -U postgres -d signal_bot -c "
  INSERT INTO market_context_snapshots (symbol, timeframe, source, bar_time, backend_regime)
  VALUES ('BTCUSDT', '5m', 'test', NOW(), 'STRONG_TREND_UP');
"

# Send signal with mismatched regime
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "YOUR_SECRET",
    "signal": "long",
    "symbol": "BTCUSDT",
    "timeframe": "5",
    "timestamp": "2026-05-04T06:30:00Z",
    "price": 68000,
    "source": "test",
    "confidence": 0.85,
    "regime": "WEAK_TREND_DOWN",
    "metadata": {
      "entry": 68000,
      "stop_loss": 67500,
      "take_profit": 69000
    }
  }'
```

Expected:
- HTTP `200`
- `decision="PASS_WARNING"` (nếu market_context.enabled=true)
- filter_results có `BACKEND_REGIME_MISMATCH` với `result=WARN`

### 9. Calibration proposals (requires dashboard token)

```bash
curl -X GET "http://localhost:8080/api/v1/analytics/calibration/proposals?days=90&min_samples=30" \
  -H "Authorization: Bearer YOUR_DASHBOARD_TOKEN"
```

Expected:
- HTTP `200`
- response có `proposals` array (có thể empty nếu chưa có đủ closed outcomes)
- mỗi proposal có `current`, `suggested`, `direction`, `confidence`, `sample_health`

### 10. Config dry-run (requires dashboard token)

```bash
curl -X POST http://localhost:8080/api/v1/admin/config/signal-bot/dry-run \
  -H "Authorization: Bearer YOUR_DASHBOARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_value": {
      "confidence_thresholds": {
        "5m": 0.81
      }
    },
    "change_reason": "Test dry-run for V1.3 smoke check"
  }'
```

Expected:
- HTTP `200`
- response có `changed_paths: ["confidence_thresholds.5m"]`
- response có `config_value` với merged config
- DB `system_configs.version` không thay đổi

### 11. Replay compare mode

```bash
# Tạo test config file
echo '{
  "allowed_symbols": ["BTCUSDT"],
  "allowed_timeframes": ["5m"],
  "confidence_thresholds": {"5m": 0.85},
  "cooldown_minutes": {"5m": 10},
  "rr_min_base": 1.5,
  "rr_min_squeeze": 2.0,
  "duplicate_price_tolerance_pct": 0.002,
  "enable_news_block": false,
  "news_block_before_min": 15,
  "news_block_after_min": 30,
  "log_reject_to_admin": true
}' > /tmp/proposed_config.json

# Run replay compare
python scripts/replay_payloads.py \
  docs/examples/sample_long_5m.json \
  --compare-config-file /tmp/proposed_config.json \
  --output /tmp/replay_compare.jsonl
```

Expected:
- Script chạy không crash
- `/tmp/replay_compare.jsonl` có records với `current_decision`, `proposed_decision`, `decision_changed`
- Console output có summary: `total`, `changed_decisions`, `main_to_warn`, etc.

## Go / No-Go

- Go nếu tất cả bước trên đúng expected behavior
- No-Go nếu thiếu audit row cho invalid request, duplicate không trả `DUPLICATE`, hoặc valid signal không persist đủ business records


## Standard verify commands

```bash
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration -q
python3 -m pytest -q
bash scripts/smoke_local.sh
```
