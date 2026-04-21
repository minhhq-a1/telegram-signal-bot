# Project Context — Telegram Signal Bot V1
<!-- Dùng file này làm context chính khi làm việc với Cursor / Claude / Copilot -->

## Dự án là gì?

Backend service nhận trading signal từ TradingView Pine Script v8.4 qua webhook, lọc 2 lớp, gửi notification lên Telegram.
**Không auto-trade.** Chỉ là signal assistant.

---

## Tech Stack

```
Python 3.12 + FastAPI + PostgreSQL 16 + httpx (async) + Pydantic v2
```

---

## Cấu trúc thư mục

```
app/
├── api/
│   ├── health_controller.py      # GET /api/v1/health
│   ├── webhook_controller.py     # POST /api/v1/webhooks/tradingview  ← CORE
│   └── signal_controller.py      # GET /api/v1/signals/{signal_id}
├── core/
│   ├── config.py                 # Pydantic Settings
│   ├── enums.py                  # SignalSide, DecisionType, RuleResult...
│   ├── logging.py
│   └── database.py               # SQLAlchemy engine + get_db()
├── domain/
│   ├── schemas.py                # Pydantic: TradingViewWebhookPayload, SignalMetadata
│   └── models.py                 # SQLAlchemy ORM: 8 tables
├── repositories/
│   ├── signal_repo.py            # find_by_signal_id(), find_recent_same_side()
│   ├── config_repo.py            # get_signal_bot_config() → dict (cached 30s)
│   └── market_event_repo.py      # find_active_around() → news block
├── services/
│   ├── auth_service.py           # validate_secret() dùng compare_digest
│   ├── signal_normalizer.py      # TradingViewWebhookPayload → dict
│   ├── filter_engine.py          # CORE LOGIC: run() → FilterExecutionResult
│   ├── message_renderer.py       # render_main(), render_warning()
│   └── telegram_notifier.py      # notify() → async httpx + retry
└── main.py
```

---

## Flow xử lý (webhook_controller)

```python
# 1. Auth + audit-first raw log
is_authed = AuthService.validate_secret(payload.secret)
webhook_event = webhook_event_repo.create(...)
if not is_authed:
    db.commit()
    raise 401

# 2. Idempotency
if signal_repo.find_by_signal_id(payload.signal_id): return DUPLICATE

# 3. Normalize
normalized = SignalNormalizer.normalize(payload)

# 4. Persist signal
signal = signal_repo.create(normalized)

# 5. Filter (boolean gate, không phải scoring)
config = config_repo.get_signal_bot_config()
result = FilterEngine(config, signal_repo, market_event_repo).run(normalized)

# 6. Persist results
filter_result_repo.bulk_insert(result.filter_results, signal.id)
decision_repo.create(result, signal.id)
db.commit()  # persist business records trước khi notify

# 7. Notify + log telegram
if result.final_decision in ("PASS_MAIN", "PASS_WARNING", "REJECT->ADMIN"):
    text = ...
    status, data = await TelegramNotifier().notify(...)
    telegram_repo.create(...)

# 8. Commit + return
db.commit()
return {"status": "accepted", "signal_id": ..., "decision": result.final_decision}
```

---

## Filter Engine — Boolean Gate (không phải scoring)

```
Phase 1 (hard, short-circuit):
  SYMBOL_ALLOWED, TIMEFRAME_ALLOWED, CONFIDENCE_RANGE, PRICE_VALID

Phase 2 (trade math):
  DIRECTION_SANITY_VALID
  MIN_RR: base>=1.5 | squeeze>=2.0

Phase 3a (hard rules — FAIL → REJECT):
  MIN_CONFIDENCE_BY_TF  1m=0.82 3m=0.80 5m=0.78 12m=0.76 15m=0.74
  REGIME_HARD_BLOCK     LONG+STRONG_TREND_DOWN | SHORT+STRONG_TREND_UP
  DUPLICATE_SUPPRESSION cùng signature + entry lệch <0.2%
  NEWS_BLOCK            active market_event

Phase 3b (advisory — WARN → routing only):
  VOLATILITY_WARNING    RANGING_HIGH_VOL=WARN_MEDIUM | SQUEEZE_BUILDING=WARN_LOW
  COOLDOWN_ACTIVE       cùng side trong cooldown window → WARN_MEDIUM
  LOW_VOLUME_WARNING    vol_ratio<0.8 → WARN_MEDIUM

Phase 4 (routing):
  FAIL present         → REJECT   (NONE)
  WARN MEDIUM+ present → PASS_WARNING (WARN)
  else                 → PASS_MAIN    (MAIN)

server_score = indicator_confidence + Σ(score_delta)
  → Lưu DB để analytics sau paper trading
  → KHÔNG dùng để quyết định pass/reject
```

---

## Payload đến từ TradingView

```python
class TradingViewWebhookPayload(BaseModel):
    # REQUIRED
    secret: str
    signal_id: str
    signal: Literal["long", "short"]
    symbol: str             # "BTCUSDT"
    timeframe: str          # "5m"
    timestamp: datetime     # ISO-8601 UTC
    price: float
    source: str
    confidence: float       # 0.0–1.0  ← heuristic, không phải win rate
    metadata: SignalMetadata

class SignalMetadata(BaseModel):
    entry: float            # REQUIRED
    stop_loss: float        # REQUIRED
    take_profit: float      # REQUIRED
    # Optional:
    signal_type: str | None  # LONG_V73 | SHORT_V73 | SHORT_SQUEEZE
    regime: str | None       # STRONG_TREND_UP/DOWN | WEAK_TREND_UP/DOWN | NEUTRAL
    vol_regime: str | None   # TRENDING_HIGH/LOW_VOL | RANGING_HIGH/LOW_VOL | SQUEEZE_BUILDING | ...
    vol_ratio: float | None  # volume / SMA20(volume)
    atr, atr_pct, adx, rsi, rsi_slope, stoch_k, macd_hist  # optional indicators
    squeeze_on, squeeze_fired, squeeze_bars                  # optional
```

---

## DB Tables

| Table | Mục đích |
|---|---|
| `webhook_events` | Raw HTTP request, log ngay kể cả invalid |
| `signals` | Normalized signal, lưu server_score để analytics |
| `signal_filter_results` | Mỗi rule chạy = 1 row |
| `signal_decisions` | Kết quả cuối (PASS_MAIN/WARNING/REJECT) |
| `telegram_messages` | Delivery log |
| `system_configs` | Config động — không hardcode threshold |
| `market_events` | Lịch sự kiện news block (nhập tay) |
| `signal_outcomes` | V2 stub — win/loss tracking |

**Thứ tự persist:** webhook_event → signal → filter_results → decision → commit → telegram

---

## Enums

```python
SignalSide:    LONG | SHORT
DecisionType:  PASS_MAIN | PASS_WARNING | REJECT | DUPLICATE
TelegramRoute: MAIN | WARN | ADMIN | NONE
RuleResult:    PASS | WARN | FAIL
RuleSeverity:  INFO | LOW | MEDIUM | HIGH | CRITICAL
```

---

## Key Design Decisions

1. **Boolean gate, không phải scoring** — FAIL/WARN quyết định route, không phải server_score threshold
2. **server_score chỉ để analytics** — tính và lưu DB, không dùng để pass/reject
3. **Persist trước notify sau** — business records được commit trước khi gọi Telegram
4. **signal_id = idempotency key** — duplicate → 200 DUPLICATE, không process lại
5. **HTF bias disabled V1** — không dùng fallback circular dependency
6. **Config từ DB** — threshold, cooldown trong `system_configs`, không hardcode

---

## Anti-patterns cần tránh

```
❌ Dùng server_score >= threshold để quyết định PASS/REJECT
❌ Implement HTF_BIAS_CHECK dùng regime từ payload (circular dependency)
❌ Tin indicator_confidence như win probability thực
❌ Expose expected_wr ra kênh Telegram chính
❌ Gửi Telegram trước db.commit()
❌ Hardcode confidence threshold trong code — dùng system_configs
❌ Dùng db.query() — SQLAlchemy 1.x style
❌ Log TRADINGVIEW_SHARED_SECRET
```

---

## Docs liên quan

| File | Nội dung |
|---|---|
| `docs/FILTER_RULES.md` | Rule engine đầy đủ + giới hạn của từng rule |
| `docs/PAYLOAD_CONTRACT.md` | Payload fields, enum values, examples |
| `docs/DATABASE_SCHEMA.md` | DDL + indexes + audit trail queries |
| `docs/API_REFERENCE.md` | Endpoint spec + Telegram format |
| `docs/TASKS.md` | Task breakdown có dependency order |
| `docs/TEST_CASES.md` | Test cases với input/output cụ thể |
