# Payload Contract — TradingView → Signal Bot V1.1

## 1. Tổng quan

TradingView gửi JSON qua `alert()` khi tín hiệu được xác nhận (`barstate.isconfirmed`).  
Bot nhận tại `POST /api/v1/webhooks/tradingview`.

**Nguồn:** Pine Script Bot Webhook v8.4 [BTC]  
**Payload version:** `v1`  
**Content-Type:** `application/json`

---

## 2. Payload đầy đủ (v1)

```json
{
  "payload_version": "v1",
  "secret": "YOUR_SHARED_SECRET",
  "signal": "long",
  "symbol": "BTCUSDT",
  "chart_symbol": "BTCUSD",
  "exchange": "KRAKEN",
  "market_type": "perp",
  "timeframe": "5m",
  "timestamp": "2026-04-18T15:30:00Z",
  "bar_time": "2026-04-18T15:30:00Z",
  "price": 68250.5,
  "source": "Bot_Webhook_v84",
  "confidence": 0.81,
  "metadata": {
    "entry": 68250.5,
    "stop_loss": 67980.0,
    "take_profit": 68740.0,
    "atr": 180.3,
    "atr_pct": 0.264,
    "adx": 21.4,
    "rsi": 31.2,
    "rsi_slope": 2.4,
    "stoch_k": 12.8,
    "macd_hist": -15.2,
    "signal_type": "LONG_V73",
    "strategy": "RSI_STOCH_V73",
    "regime": "WEAK_TREND_DOWN",
    "vol_regime": "TRENDING_LOW_VOL",
    "squeeze_on": 0,
    "squeeze_fired": 0,
    "squeeze_bars": 0,
    "kc_position": 0.21,
    "atr_percentile": 62.0,
    "expected_wr": "68.2%",
    "bar_confirmed": true,
    "vol_ratio": 1.24
  }
}
```

---

## 3. Required fields

| Field | Type | Mô tả |
|---|---|---|
| `secret` | string | Shared secret để xác thực. Phải khớp `TRADINGVIEW_SHARED_SECRET` |
| `signal` | enum | `"long"` hoặc `"short"` |
| `symbol` | string | Symbol backend dùng để trade. VD: `"BTCUSDT"` |
| `timeframe` | string | Timeframe hiện tại. Chấp nhận cả format TradingView native như `"3"`, `"60"`, `"1D"`, `"30S"` và format nội bộ như `"3m"`, `"1h"` |
| `timestamp` | ISO-8601 | Thời điểm alert được gửi (UTC) |
| `price` | float | Giá đóng cửa của bar |
| `source` | string | Tên indicator. VD: `"Bot_Webhook_v84"` |
| `confidence` | float [0–1] | Confidence score từ indicator |
| `metadata.entry` | float | Giá vào lệnh (= `price`) |
| `metadata.stop_loss` | float | Giá stop loss |
| `metadata.take_profit` | float | Giá take profit |

---

## 4. Optional fields (recommended)

| Field | Type | Mô tả |
|---|---|---|
| `payload_version` | string | `"v1"` — versioning cho backward compat |
| `signal_id` | string | Idempotency key. Có thể gửi sẵn; nếu thiếu thì server sẽ tự generate deterministic từ payload |
| `chart_symbol` | string | Symbol trên chart TradingView. VD: `"BTCUSD"` |
| `exchange` | string | Exchange trên chart. VD: `"KRAKEN"`, `"BINANCE"` |
| `market_type` | enum | `"spot"` / `"perp"` / `"futures"` |
| `bar_time` | ISO-8601 | Thời điểm mở bar (UTC) |
| `metadata.atr` | float | ATR tuyệt đối |
| `metadata.atr_pct` | float | ATR % so với giá |
| `metadata.adx` | float | ADX value |
| `metadata.rsi` | float | RSI 14 |
| `metadata.rsi_slope` | float | RSI slope (5 bar) |
| `metadata.stoch_k` | float | Stochastic K |
| `metadata.macd_hist` | float | MACD histogram |
| `metadata.signal_type` | string | `"LONG_V73"` / `"SHORT_V73"` / `"SHORT_SQUEEZE"` |
| `metadata.strategy` | string | `"RSI_STOCH_V73"` / `"KELTNER_SQUEEZE"` |
| `metadata.regime` | string | Trend regime (xem bên dưới) |
| `metadata.vol_regime` | string | Volatility regime (xem bên dưới) |
| `metadata.squeeze_on` | int (0/1) | Bollinger đang trong Keltner |
| `metadata.squeeze_fired` | int (0/1) | Squeeze vừa kết thúc bar này |
| `metadata.squeeze_bars` | int | Số bar squeeze liên tiếp |
| `metadata.kc_position` | float | Vị trí giá trong Keltner Channel [0–1] |
| `metadata.atr_percentile` | float | ATR percentile (50 bar lookback) |
| `metadata.expected_wr` | string | Win rate ước tính (HEURISTIC — không dùng để quảng bá) |
| `metadata.bar_confirmed` | bool | Luôn `true` (indicator chỉ alert khi confirmed) |
| `metadata.vol_ratio` | float | Volume / Volume SMA(20) |

---

## 5. Enum values

### `metadata.regime`

| Value | Ý nghĩa |
|---|---|
| `STRONG_TREND_UP` | EMA20 > EMA50 > EMA200, giá trên EMA200 |
| `STRONG_TREND_DOWN` | EMA20 < EMA50 < EMA200, giá dưới EMA200 |
| `WEAK_TREND_UP` | Giá trên EMA200, không phải strong trend (**BLOCK — 0% WR**) |
| `WEAK_TREND_DOWN` | Giá dưới EMA200, không phải strong trend |
| `NEUTRAL` | Không xác định |

### `metadata.vol_regime`

| Value | Ý nghĩa | Bot action |
|---|---|---|
| `TRENDING_HIGH_VOL` | ADX ≥ 25, ATR percentile ≥ 70 | +0.03 score |
| `TRENDING_LOW_VOL` | ADX ≥ 25, ATR percentile < 70 | neutral |
| `RANGING_HIGH_VOL` | ADX < 20, ATR percentile ≥ 70 | −0.08 score, WARN |
| `RANGING_LOW_VOL` | ADX < 20, ATR low | neutral |
| `SQUEEZE_BUILDING` | BB trong Keltner ≥ 3 bars | −0.03 score, WARN |
| `BREAKOUT_IMMINENT` | Squeeze vừa kết thúc | neutral |
| `TRANSITIONAL` | Không thuộc nhóm nào | neutral |

### `metadata.signal_type`

| Value | Nguồn gốc | SL/TP multiplier |
|---|---|---|
| `LONG_V73` | RSI + Stoch + Slope + ADX | SL: ATR×1.5, TP: ATR×2.5 |
| `SHORT_V73` | RSI + Stoch + Slope + ADX | SL: ATR×1.5, TP: ATR×2.5 |
| `SHORT_SQUEEZE` | Keltner Squeeze + MACD momentum | SL: ATR×1.2, TP: ATR×3.0 |

---

## 6. Validation rules (server-side)

### Required field check
```
Reject 400 nếu thiếu bất kỳ required field nào
```

### Type validation
```
confidence ∈ [0.0, 1.0]
price > 0
entry > 0
stop_loss > 0
take_profit > 0
signal ∈ {"long", "short"}
```

### Direction sanity
```
LONG:  stop_loss < entry < take_profit
SHORT: take_profit < entry < stop_loss
```

### Symbol & Timeframe whitelist
```
Allowed symbols:    BTCUSDT, BTCUSD
Allowed timeframes: 1m, 3m, 5m, 12m, 15m, 30m, 1h
```
> TF 30S, 45S, 2m, 4m, 6m–11m, 13m–20m, 4h, 1d bị reject bởi server (quá nhiều noise, thiếu tuning backend, hoặc chưa nằm trong rollout hiện tại)

Ví dụ normalize từ TradingView native:
- `3` → `3m`
- `60` → `1h`
- `1D` → `1d`
- `30S` → `30s`

---

## 7. Format signal_id

Format chuẩn có thể được generate bởi Pine Script hoặc bởi server nếu client không gửi `signal_id`:

```
tv-{symbol_lower}-{timeframe}-{bar_time_unix_ms}-{side_lower}-{signal_type_lower}
```

Ví dụ:
```
tv-btcusdt-5m-1713452400000-long-long_v73
tv-btcusdt-3m-1713452280000-short-short_squeeze
```

`signal_id` là idempotency key của hệ thống.

Client **có thể gửi sẵn** `signal_id`, nhưng nếu thiếu thì server sẽ tự generate một giá trị deterministic từ:
- `symbol`
- `timeframe` sau khi normalize
- `bar_time` hoặc `timestamp`
- `signal`
- `metadata.entry`
- `metadata.stop_loss`
- `metadata.take_profit`
- `metadata.signal_type`

Thiết kế này giúp:
- duplicate cùng business event vẫn nhận ra được
- không còn phụ thuộc việc TradingView phải tự ghép `signal_id`
- tránh fallback yếu chỉ dựa trên `price`

---

## 8. Response format

### Success
```json
{
  "status": "accepted",
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "decision": "PASS_MAIN"
}
```

`decision` values: `PENDING`, `PASS_MAIN`, `PASS_WARNING`, `REJECT`, `DUPLICATE`

### Error responses

```json
{ "status": "rejected", "error_code": "INVALID_SECRET",      "message": "Webhook authentication failed" }
{ "status": "rejected", "error_code": "INVALID_JSON",        "message": "Request body is not valid JSON" }
{ "status": "rejected", "error_code": "INVALID_SCHEMA",      "message": "Request body does not match webhook schema" }
{ "status": "rejected", "error_code": "UNSUPPORTED_SYMBOL",  "message": "Symbol ETHUSDT not in whitelist" }
{ "status": "rejected", "error_code": "UNSUPPORTED_TIMEFRAME","message": "Timeframe 30S not allowed in V1" }
{ "status": "rejected", "error_code": "INVALID_SIGNAL_VALUES","message": "Direction check failed: SL >= entry for LONG" }
{ "status": "accepted", "signal_id": "...",  "decision": "DUPLICATE" }
```

---

## 9. Ví dụ payload SHORT_SQUEEZE

```json
{
  "payload_version": "v1",
  "secret": "YOUR_SHARED_SECRET",
  "signal_id": "tv-btcusdt-3m-1713452280000-short-short_squeeze",
  "signal": "short",
  "symbol": "BTCUSDT",
  "chart_symbol": "BTCUSD",
  "exchange": "KRAKEN",
  "market_type": "perp",
  "timeframe": "3m",
  "timestamp": "2026-04-18T15:28:00Z",
  "bar_time": "2026-04-18T15:27:00Z",
  "price": 68910.0,
  "source": "Bot_Webhook_v84",
  "confidence": 0.87,
  "metadata": {
    "entry": 68910.0,
    "stop_loss": 69121.0,
    "take_profit": 68277.0,
    "atr": 140.7,
    "atr_pct": 0.204,
    "adx": 19.2,
    "rsi": 71.4,
    "rsi_slope": -3.2,
    "stoch_k": 88.3,
    "macd_hist": -42.1,
    "signal_type": "SHORT_SQUEEZE",
    "strategy": "KELTNER_SQUEEZE",
    "regime": "WEAK_TREND_DOWN",
    "vol_regime": "BREAKOUT_IMMINENT",
    "squeeze_on": 0,
    "squeeze_fired": 1,
    "squeeze_bars": 6,
    "mom_direction": -1,
    "kc_position": 0.78,
    "atr_percentile": 74.0,
    "expected_wr": "53.8%",
    "bar_confirmed": true,
    "vol_ratio": 2.31
  }
}
```

---

## 10. Ghi chú quan trọng

> **`expected_wr` là heuristic** — được hardcode theo TF trong Pine Script.  
> Không nên dùng để đánh giá chất lượng tín hiệu thực tế.  
> Bot không hiển thị `expected_wr` ra kênh Telegram chính.

> **Indicator confidence** được tính theo công thức:  
> `base_confidence_by_TF + RSI/Stoch modifiers + regime modifiers`  
> → Chỉ là input cho `server_score`, không phải xác suất thắng.

> **`bar_confirmed: true`** luôn đúng vì Pine Script chỉ gửi khi `barstate.isconfirmed`.  
> Bot vẫn lưu field này để audit trail.
