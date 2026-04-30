# Project Context — Telegram Signal Bot V1.1
<!-- Dùng file này làm context chính khi làm việc với Cursor / Claude / Copilot -->

## Dự án là gì?

Backend service nhận trading signal từ TradingView Pine Script v8.4 qua webhook, lọc 2 lớp, gửi notification lên Telegram, cung cấp dashboard/analytics/reverify admin.
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
│   └── models.py                 # SQLAlchemy ORM: core tables + V1.1 reverify
├── repositories/
│   ├── signal_repo.py            # idempotency, duplicate/cooldown queries
│   ├── config_repo.py            # get_signal_bot_config() → dict (cached 30s)
│   └── market_event_repo.py      # find_active_around() → news block
├── services/
│   ├── auth_service.py           # validate_secret() dùng compare_digest
│   ├── signal_normalizer.py      # TradingViewWebhookPayload → dict
│   ├── filter_engine.py          # CORE LOGIC: run() → FilterExecutionResult
│   ├── strategy_validator.py     # V1.1 strategy-specific validation
│   ├── rescoring_engine.py       # V1.1 backend rescoring
│   ├── message_renderer.py       # render_main(), render_warning(), render_reject_admin()
│   └── telegram_notifier.py      # notify() → (status, response, error_detail)
└── main.py
```

---

## Flow xử lý hiện tại

```python
# webhook_controller.py
raw_body_text = (await request.body()).decode("utf-8", errors="replace")
result = await WebhookIngestionService(...).ingest(raw_body_text, source_ip, headers)

if result.is_error:
    return JSONResponse(status_code=result.status_code, content=result.body.model_dump(mode="json"))

if result.notification_job is not None:
    background_tasks.add_task(service.deliver_notification, result.notification_job)

return result.body
```

`WebhookIngestionService.ingest()` order:

```text
1. parse raw JSON; invalid JSON → webhook_events + commit + 400
2. validate schema; invalid schema → webhook_events + commit + 400
3. validate secret using compare_digest
4. insert webhook_events with redacted headers/body
5. invalid secret → mark auth failure + commit + 401
6. idempotency by signal_id → 200 DUPLICATE, no duplicate signal insert
7. normalize payload
8. insert signal; IntegrityError race can resolve to DUPLICATE
9. load DB config
10. FilterEngine.run() boolean gate
11. persist server_score, filter_results, decision
12. build notification job for PASS_MAIN/PASS_WARNING or reject-admin
13. commit business records
14. return response; background task sends Telegram and writes telegram_messages
```

Persist order: `webhook_events → signals → filter_results → decision → commit → Telegram background → telegram_messages commit`.

---


## Filter Engine — Boolean Gate (không phải scoring)

```
Phase 1 (hard, short-circuit):
  SYMBOL_ALLOWED, TIMEFRAME_ALLOWED, CONFIDENCE_RANGE, PRICE_VALID

Phase 2 (trade math):
  DIRECTION_SANITY_VALID
  MIN_RR: base>=1.5 | squeeze>=2.0

Phase 3a (hard rules — FAIL → REJECT):
  MIN_CONFIDENCE_BY_TF  1m=0.82 3m=0.80 5m=0.78 12m=0.76 15m=0.74 30m=0.72 1h=0.70
  REGIME_HARD_BLOCK     LONG+STRONG_TREND_DOWN | SHORT+STRONG_TREND_UP
  DUPLICATE_SUPPRESSION cùng signature + entry lệch <0.2%
  NEWS_BLOCK            HIGH impact market_event trong configured window

Phase 3b (advisory — WARN → routing only):
  VOLATILITY_WARNING    RANGING_HIGH_VOL=WARN_MEDIUM | SQUEEZE_BUILDING=WARN_LOW
  COOLDOWN_ACTIVE       prior PASS_MAIN cùng side trong cooldown window → WARN_MEDIUM
  LOW_VOLUME_WARNING    vol_ratio<0.8 → WARN_MEDIUM

Phase 2.5 / 3c / 3d (V1.1 pilot):
  STRATEGY_VALIDATION  hard strategy FAIL + quality floor WARN
  RR_PROFILE_MATCH     ngoài target ± tolerance → WARN_MEDIUM
  BACKEND_SCORE_THRESHOLD score<threshold → WARN_MEDIUM

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
    strategy: str | None     # RSI_STOCH_V73 | KELTNER_SQUEEZE
    mom_direction: int | None # -1/0/1
    regime: str | None       # STRONG_TREND_UP/DOWN | WEAK_TREND_UP/DOWN | NEUTRAL
    vol_regime: str | None   # TRENDING_HIGH/LOW_VOL | RANGING_HIGH/LOW_VOL | SQUEEZE_BUILDING | ...
    vol_ratio: float | None  # volume / SMA20(volume)
    atr, atr_pct, adx, rsi, rsi_slope, stoch_k, macd_hist  # optional indicators
    squeeze_on, squeeze_fired, squeeze_bars                  # optional
    kc_position, atr_percentile                               # optional V1.1
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
| `signal_reverify_results` | V1.1 reverify audit log |

**Thứ tự persist:** webhook_event → signal → filter_results → decision → commit → telegram background → telegram_messages

---

## Enums

```python
SignalSide:    LONG | SHORT
DecisionType:  PENDING | PASS_MAIN | PASS_WARNING | REJECT | DUPLICATE
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
6. **Config từ DB** — threshold, cooldown, V1.1 strategy/rescoring config trong `system_configs`, không hardcode

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
| `docs/CHANGELOG_V1.1.md` | V1.1 changes |
| `docs/POST_V11_OPTIMIZATION_PLAN.md` | Post-V1.1 backlog/context |
