# API Reference — Signal Bot V1

**Base URL:** `https://your-domain.com`
**API Version:** `v1` (app `1.1.0`)
**Auth:** Shared secret trong request body (không dùng Authorization header)

---

## Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/webhooks/tradingview` | Nhận alert từ TradingView |
| `GET` | `/api/v1/signals/{signal_id}` | Debug: xem chi tiết signal |
| `POST` | `/api/v1/signals/{signal_id}/reverify` | Replay filter với config hiện tại |
| `GET` | `/api/v1/signals/{signal_id}/reverify-results` | Xem lịch sử reverify |

---

## GET `/api/v1/health`

Kiểm tra service còn sống.

### Response `200 OK`

```json
{
  "status": "ok",
  "service": "telegram-signal-bot",
  "version": "1.1.0"
}
```

---

## POST `/api/v1/webhooks/tradingview`

Endpoint chính. Nhận JSON alert từ TradingView Pine Script.

### Headers

```
Content-Type: application/json
```

### Request Body

Xem [PAYLOAD_CONTRACT.md](./PAYLOAD_CONTRACT.md) để biết đầy đủ.

**Minimum payload:**
```json
{
  "secret": "YOUR_SHARED_SECRET",
  "signal": "long",
  "symbol": "BTCUSDT",
  "timeframe": "5",
  "timestamp": "2026-04-18T15:30:00Z",
  "price": 68250.5,
  "source": "Bot_Webhook_v84",
  "confidence": 0.81,
  "metadata": {
    "entry": 68250.5,
    "stop_loss": 67980.0,
    "take_profit": 68740.0
  }
}
```

`signal_id` là optional ở request. Nếu thiếu, server sẽ tự generate idempotency key deterministic từ payload sau khi normalize timeframe.

Timeframe được chấp nhận theo cả 2 kiểu:
- TradingView native: `3`, `60`, `1D`, `30S`
- Internal canonical: `3m`, `1h`, `1d`, `30s`

### Response `200 OK` — Accepted

```json
{
  "status": "accepted",
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "decision": "PASS_MAIN",
  "timestamp": "2026-04-18T15:30:02Z"
}
```

`decision` values:

| Value | Ý nghĩa |
|---|---|
| `PENDING` | Đang xử lý (async) |
| `PASS_MAIN` | Gửi kênh chính |
| `PASS_WARNING` | Gửi kênh warning |
| `REJECT` | Bị lọc, không gửi |
| `DUPLICATE` | `signal_id` đã tồn tại, bỏ qua |

### Response `200 OK` — Duplicate

```json
{
  "status": "accepted",
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "decision": "DUPLICATE"
}
```

> **Lưu ý:** TradingView đôi khi gửi lại cùng alert. Bot trả `200` cho duplicate để TradingView không retry.

### Response `400 Bad Request` — Invalid JSON

```json
{
  "status": "rejected",
  "error_code": "INVALID_JSON",
  "message": "Request body is not valid JSON"
}
```

### Response `400 Bad Request` — Invalid Schema

```json
{
  "status": "rejected",
  "error_code": "INVALID_SCHEMA",
  "message": "Request body does not match webhook schema"
}
```

Ví dụ các case thuộc `INVALID_SCHEMA`:
- thiếu `signal_id`
- `signal_id` là chuỗi rỗng
- thiếu `metadata.entry`, `metadata.stop_loss`, hoặc `metadata.take_profit`

**Lưu ý về error responses hiện tại:**

| Case | HTTP | Runtime behavior |
|---|---|---|
| Invalid JSON | `400` | custom `ErrorResponse`, vẫn tạo audit row với `is_valid_json=false` |
| Invalid schema | `400` | custom `ErrorResponse`, vẫn tạo audit row với `is_valid_json=true` |
| Invalid secret | `401` | custom `ErrorResponse` |
| Signal not found | `404` | `HTTPException(detail="Signal not found")` |

`UNSUPPORTED_SYMBOL`, `UNSUPPORTED_TIMEFRAME`, `INVALID_SIGNAL_VALUES` hiện không được raise ở API boundary dưới dạng custom error body; chúng đi qua filter/persist flow hiện tại.

### Response `401 Unauthorized`

```json
{
  "status": "rejected",
  "error_code": "INVALID_SECRET",
  "message": "Webhook authentication failed"
}
```

---

## GET `/api/v1/signals/{signal_id}`

**Internal/admin only.** Dùng để debug.

### Path Parameters

| Param | Type | Mô tả |
|---|---|---|
| `signal_id` | string | Signal ID từ payload |

### Response `200 OK`

```json
{
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "signal": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
    "side": "LONG",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "entry_price": 68250.5,
    "stop_loss": 67980.0,
    "take_profit": 68740.0,
    "risk_reward": 1.81,
    "indicator_confidence": 0.81,
    "server_score": 0.84,
    "signal_type": "LONG_V73",
    "strategy": "RSI_STOCH_V73",
    "regime": "WEAK_TREND_DOWN",
    "vol_regime": "TRENDING_LOW_VOL",
    "created_at": "2026-04-18T15:30:02Z"
  },
  "decision": {
    "decision": "PASS_MAIN",
    "decision_reason": "Passed all filters",
    "telegram_route": "MAIN",
    "created_at": "2026-04-18T15:30:02Z"
  },
  "filter_results": [
    {
      "rule_code": "SYMBOL_ALLOWED",
      "rule_group": "validation",
      "result": "PASS",
      "severity": "INFO",
      "score_delta": 0.0,
      "details": null
    },
    {
      "rule_code": "MIN_CONFIDENCE_BY_TF",
      "rule_group": "trading",
      "result": "PASS",
      "severity": "INFO",
      "score_delta": 0.0,
      "details": {"required": 0.78, "actual": 0.81}
    },
    {
      "rule_code": "VOLATILITY_WARNING",
      "rule_group": "trading",
      "result": "PASS",
      "severity": "INFO",
      "score_delta": 0.03,
      "details": {"vol_regime": "TRENDING_HIGH_VOL"}
    }
  ],
  "telegram_messages": [
    {
      "channel_type": "MAIN",
      "chat_id": "-100xxxxxxxxx",
      "message_text": "🟢 BTCUSDT LONG | 5m\n...",
      "delivery_status": "SENT",
      "sent_at": "2026-04-18T15:30:03Z"
    }
  ]
}
```

### Response `404 Not Found`

```json
{
  "detail": "Signal not found"
}
```

---

## POST `/api/v1/signals/{signal_id}/reverify`

**Internal/admin only.** Replay filter engine bằng persisted DB snapshot và config hiện tại. Endpoint này không mutate signal/decision gốc; mỗi lần gọi chỉ append audit row vào `signal_reverify_results`.

Legacy compatibility: `signal_type` và `strategy` có thể thiếu trên signal cũ. Khi thiếu, strategy-specific checks và rescoring theo `signal_type` sẽ tự skip; core trade filters vẫn chạy nếu đủ `entry_price`, `risk_reward`, và `indicator_confidence`.

### Response `200 OK`

```json
{
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "original_decision": "PASS_MAIN",
  "reverify_decision": "PASS_WARNING",
  "reverify_score": 72,
  "reject_code": null,
  "decision_reason": "Warnings triggered: BACKEND_SCORE_THRESHOLD"
}
```

### Response `422 Unprocessable Entity`

Trả về khi persisted snapshot thiếu field core bắt buộc để replay.

```json
{
  "detail": {
    "reason": "missing_required_persisted_fields",
    "missing_fields": ["risk_reward"],
    "message": "Cannot reverify: required persisted signal fields are missing. This may indicate a schema migration issue or incomplete data."
  }
}
```

---

## GET `/api/v1/signals/{signal_id}/reverify-results`

**Internal/admin only.** Trả về audit history đã persist từ các lần reverify, mới nhất trước.

### Response `200 OK`

```json
{
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "count": 1,
  "results": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "original_decision": "PASS_MAIN",
      "reverify_decision": "PASS_WARNING",
      "reverify_score": 72,
      "reject_code": null,
      "decision_reason": "Warnings triggered: BACKEND_SCORE_THRESHOLD",
      "score_items": ["base=72"],
      "filter_results": [
        {"rule_code": "BACKEND_SCORE_THRESHOLD", "result": "WARN", "severity": "MEDIUM"}
      ],
      "created_at": "2026-04-30T06:10:00Z"
    }
  ]
}
```

### Response `404 Not Found`

```json
{
  "detail": "Signal not found"
}
```

---

## Telegram Message Format

### PASS_MAIN — kênh chính

```
🟢 BTCUSDT LONG | 5m
Entry: 68,250.50
SL: 67,980.00
TP: 68,740.00
RR: 1.81
Conf: 81% | Score: 84%

Type: LONG_V73
Trend: WEAK_TREND_DOWN
Vol: TRENDING_LOW_VOL

RSI: 31.2 | Slope: 2.4
StochK: 12.8 | ADX: 21.4
ATR%: 0.264

Status: PASSED ✅
Time: 22:30 ICT
Source: Bot_Webhook_v84
```

### PASS_WARNING — kênh warning

```
🟡 WARNING | BTCUSDT LONG | 5m
Reason: COOLDOWN_ACTIVE
Conf: 81% | Score: 77%
RR: 1.81
Trend: WEAK_TREND_DOWN
Vol: RANGING_HIGH_VOL
Signal ID: tv-btcusdt-5m-...
```

`Reason` hiện được build từ danh sách `rule_code` có kết quả `WARN`, không phải từ score threshold.

### REJECT — chỉ gửi admin (nếu `LOG_REJECT_TO_ADMIN=true`)

```
⛔ REJECTED | BTCUSDT SHORT | 5m
Reason: Confidence below threshold for 5m (required: 0.78, actual: 0.75)
Signal ID: tv-btcusdt-5m-...
```

---

## TradingView Alert Setup

Trong Pine Script, URL webhook được điền vào `Alert → Webhook URL`:

```
https://your-domain.com/api/v1/webhooks/tradingview
```

Message body sử dụng `{{strategy.order.alert_message}}` hoặc hardcode JSON trong `alert()`.

**Lưu ý:**
- Mỗi timeframe cần tạo 1 alert riêng
- Chỉ bật alert cho TF whitelist: `1m, 3m, 5m, 12m, 15m`
- Không bật 30S, 45S — bot sẽ reject với `UNSUPPORTED_TIMEFRAME`
