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

## Go / No-Go

- Go nếu tất cả bước trên đúng expected behavior
- No-Go nếu thiếu audit row cho invalid request, duplicate không trả `DUPLICATE`, hoặc valid signal không persist đủ business records
