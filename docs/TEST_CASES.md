# Test Cases — Signal Bot V1
<!-- File này là catalog nghiệp vụ. Không dùng làm test harness chuẩn. -->

## Cách dùng file này

- Dùng file này để hiểu `TC` và expected behavior ở mức nghiệp vụ.
- Khi viết test mới, ưu tiên bám theo fixture và setup thật trong:
  - [tests/integration/conftest.py](/Users/minhhq/Documents/telegram-signal-bot/tests/integration/conftest.py:1)
  - [tests/integration/test_api_regressions.py](/Users/minhhq/Documents/telegram-signal-bot/tests/integration/test_api_regressions.py:1)
- Không copy nguyên các ví dụ cũ dùng `db.query(...)` hoặc PostgreSQL local cứng; repo hiện đang theo SQLAlchemy 2.0 style và harness integration thực tế đang chạy với `db_session`.

## Base payload reference

Payload tham chiếu hiện tại:

```json
{
  "secret": "test-secret",
  "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
  "signal": "long",
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "timestamp": "2026-04-18T15:30:00Z",
  "bar_time": "2026-04-18T15:30:00Z",
  "price": 68250.5,
  "source": "Bot_Webhook_v84",
  "confidence": 0.82,
  "metadata": {
    "entry": 68250.5,
    "stop_loss": 67980.0,
    "take_profit": 68740.0,
    "signal_type": "LONG_V73",
    "regime": "WEAK_TREND_DOWN",
    "vol_regime": "TRENDING_LOW_VOL",
    "rsi": 31.2,
    "stoch_k": 12.8,
    "adx": 21.4,
    "atr": 180.3,
    "atr_pct": 0.264,
    "vol_ratio": 1.24,
    "bar_confirmed": true
  }
}
```

Mapping coverage thực tế xem tại:
- [docs/QA_COVERAGE_MATRIX.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_COVERAGE_MATRIX.md:1)

---

## TC-001: Valid LONG 5m → PASS_MAIN

**Mô tả:** Happy path. Signal đủ điều kiện, confidence đủ, RR đủ, regime không block.

**Input:**
```python
payload = make_payload()
# confidence=0.82, timeframe="5m", threshold=0.78 → pass
# entry=68250.5, sl=67980.0, tp=68740.0
# risk=270.5, reward=489.5, rr=1.81 → pass (>=1.5)
# regime="WEAK_TREND_DOWN" → không block LONG
```

**Expected:**
```python
response.status_code == 200
response.json() == {
    "status": "accepted",
    "signal_id": "tv-btcusdt-5m-1713452400000-long-long_v73",
    "decision": "PASS_MAIN"
}
# DB assertions:
db.query(Signal).filter_by(signal_id="tv-btcusdt-5m-...").count() == 1
db.query(SignalDecision).filter_by(decision="PASS_MAIN").count() == 1
```

---

## TC-002: Secret sai → 401

**Input:**
```python
payload = make_payload()
payload["secret"] = "wrong-secret"
```

**Expected:**
```python
response.status_code == 401
response.json()["error_code"] == "INVALID_SECRET"
# DB: webhook_events có row với auth_status="INVALID_SECRET"
# DB: signals KHÔNG có row
```

---

## TC-003: Timeframe 30S → 400 UNSUPPORTED_TIMEFRAME

**Input:**
```python
payload = make_payload(timeframe="30S")
```

**Expected:**
```python
response.status_code == 400
response.json()["error_code"] == "UNSUPPORTED_TIMEFRAME"
```

**Cũng test các TF bị reject khác:** `45S`, `2m`, `4m`, `6m`, `11m`, `13m`, `20m`

---

## TC-004: Confidence thấp hơn ngưỡng TF → REJECT

**Input:**
```python
# 5m cần >= 0.78, gửi 0.77
payload = make_payload(confidence=0.77)
```

**Expected:**
```python
response.status_code == 200  # vẫn 200, chỉ decision là REJECT
response.json()["decision"] == "REJECT"
# DB: signal_decisions có decision="REJECT"
# DB: signal_filter_results có rule_code="MIN_CONFIDENCE_BY_TF" với result="FAIL"
```

**Test thêm các ngưỡng:**
```python
# 1m cần 0.82 → test với 0.81 (REJECT) và 0.82 (PASS)
# 15m cần 0.74 → test với 0.73 (REJECT) và 0.74 (PASS)
```

---

## TC-005: Direction sai → REJECT với INVALID_SIGNAL_VALUES

**Input LONG direction sai:**
```python
payload = make_payload()
payload["metadata"]["stop_loss"] = 68500.0   # sl > entry → sai
payload["metadata"]["take_profit"] = 67000.0  # tp < entry → sai
```

**Expected:**
```python
response.status_code == 400
response.json()["error_code"] == "INVALID_SIGNAL_VALUES"
```

**Input SHORT direction sai:**
```python
payload = make_payload(signal="short")
payload["metadata"]["stop_loss"] = 67000.0   # sl < entry → sai cho SHORT
payload["metadata"]["take_profit"] = 69000.0  # tp > entry → sai cho SHORT
```

**Expected:** 400 INVALID_SIGNAL_VALUES

---

## TC-006: Duplicate signal_id → 200 DUPLICATE, không insert lại

**Input:** Gửi cùng payload 2 lần.

**Expected lần 1:**
```python
response.json()["decision"] == "PASS_MAIN"
db.query(Signal).count() == 1
```

**Expected lần 2:**
```python
response.status_code == 200
response.json()["decision"] == "DUPLICATE"
db.query(Signal).count() == 1  # vẫn chỉ 1, không insert thêm
```

---

## TC-007: Regime STRONG_TREND_DOWN block LONG → REJECT

**Input:**
```python
payload = make_payload()
payload["metadata"]["regime"] = "STRONG_TREND_DOWN"
```

**Expected:**
```python
response.json()["decision"] == "REJECT"
# filter_results có REGIME_HARD_BLOCK với result="FAIL"
```

**Test thêm:** SHORT với `regime="STRONG_TREND_UP"` → REJECT

---

## TC-008: RR thấp hơn ngưỡng → REJECT

**Input base trade:**
```python
payload = make_payload()
# Đặt tp gần entry để rr < 1.5
# entry=68250.5, sl=67980.0 → risk=270.5
# tp cần: reward < 1.5 * 270.5 = 405.75 → tp < 68656.25
payload["metadata"]["take_profit"] = 68500.0
# rr = (68500-68250.5)/(68250.5-67980) = 249.5/270.5 = 0.92 → < 1.5
```

**Expected:**
```python
response.json()["decision"] == "REJECT"
# filter_results có MIN_RR_REQUIRED với result="FAIL"
```

**Input squeeze trade:**
```python
payload = make_payload(signal="short")
payload["metadata"]["signal_type"] = "SHORT_SQUEEZE"
payload["metadata"]["entry"] = 68910.0
payload["metadata"]["stop_loss"] = 69080.0   # risk=170
payload["metadata"]["take_profit"] = 68580.0  # reward=330, rr=1.94 < 2.0 → REJECT
```

---

## TC-009: RANGING_HIGH_VOL → PASS_WARNING (boolean gate, không phụ thuộc score)

**Mô tả:** RANGING_HIGH_VOL tạo WARN MEDIUM → route sang WARNING channel.
Kết quả là PASS_WARNING bất kể confidence cao hay thấp — vì routing dựa trên WARN MEDIUM present,
không dựa trên server_score threshold.

**Input:**
```python
# Bất kể confidence bao nhiêu, RANGING_HIGH_VOL → PASS_WARNING
payload = make_payload(confidence=0.82)
payload["metadata"]["vol_regime"] = "RANGING_HIGH_VOL"
```

**Expected:**
```python
response.json()["decision"] == "PASS_WARNING"  # WARN MEDIUM → warning channel
response.json()["status"] == "accepted"
# filter_results có VOLATILITY_WARNING với result="WARN", severity="MEDIUM"
# server_score sẽ thấp hơn (0.82 - 0.08 = 0.74) nhưng không phải lý do PASS_WARNING
# Lý do PASS_WARNING là: có WARN MEDIUM present, không có FAIL
```

**Test thêm — confidence thấp hơn cũng vẫn PASS_WARNING (không REJECT):**
```python
payload = make_payload(confidence=0.79)  # vừa đủ ngưỡng 5m=0.78
payload["metadata"]["vol_regime"] = "RANGING_HIGH_VOL"
response.json()["decision"] == "PASS_WARNING"  # WARN MEDIUM → warning, không reject
```

---

## TC-010: Cooldown active → PASS_WARNING

**Setup:** Insert signal PASS_MAIN cùng symbol/timeframe/side 3 phút trước (< 10 phút cooldown 5m).

**Input:** Gửi signal mới cùng symbol/timeframe/side nhưng `signal_id` khác.

**Expected:**
```python
response.json()["decision"] == "PASS_WARNING"  # COOLDOWN = WARN MEDIUM → warning
# filter_results có COOLDOWN_ACTIVE với result="WARN", severity="MEDIUM"
# Dù confidence=0.99, cooldown WARN MEDIUM vẫn downgrade sang WARNING
# server_score giảm vì -0.10 delta nhưng không phải lý do routing
```

---

## TC-011: Missing required field → 400 INVALID_SCHEMA

**Test từng required field:**
```python
for field in ["secret", "signal_id", "signal", "symbol", "timeframe",
              "timestamp", "price", "source", "confidence"]:
    payload = make_payload()
    del payload[field]
    response = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_SCHEMA"

for field in ["entry", "stop_loss", "take_profit"]:
    payload = make_payload()
    del payload["metadata"][field]
    response = client.post("/api/v1/webhooks/tradingview", json=payload)
    assert response.status_code == 400
```

---

## TC-012: Symbol không trong whitelist → 400

**Input:**
```python
payload = make_payload(symbol="ETHUSDT")
```

**Expected:**
```python
response.status_code == 400
response.json()["error_code"] == "UNSUPPORTED_SYMBOL"
```

---

## TC-013: SHORT_SQUEEZE signal flow

**Input:**
```python
payload = make_payload(
    signal="short",
    confidence=0.87,
    **{
        "metadata": {
            "entry": 68910.0,
            "stop_loss": 69121.0,   # risk=211
            "take_profit": 68277.0,  # reward=633, rr=3.0 → pass (>=2.0)
            "signal_type": "SHORT_SQUEEZE",
            "strategy": "KELTNER_SQUEEZE",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "BREAKOUT_IMMINENT",
            "squeeze_on": 0,
            "squeeze_fired": 1,
            "squeeze_bars": 6,
        }
    }
)
```

**Expected:**
```python
response.json()["decision"] == "PASS_MAIN"
# DB: signal có signal_type="SHORT_SQUEEZE"
# DB: risk_reward ≈ 3.0
```

---

## TC-014: Telegram retry on timeout

**Setup:** Mock Telegram API fail lần 1 (timeout), thành công lần 2.

```python
# Dùng httpx mock
import respx

@respx.mock
def test_telegram_retry():
    # Lần 1: timeout
    respx.post("https://api.telegram.org/...").mock(side_effect=httpx.TimeoutException)
    # Lần 2: success
    respx.post("https://api.telegram.org/...").mock(return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 123}}))

    notifier = TelegramNotifier()
    status, data = asyncio.run(notifier.notify("MAIN", "test message"))

    assert status == "SENT"
    assert data["result"]["message_id"] == 123
```

---

## TC-015: GET /signals/{signal_id} trả đúng detail

**Setup:** Insert signal qua POST webhook.

**Input:**
```python
signal_id = "tv-btcusdt-5m-1713452400000-long-long_v73"
response = client.get(f"/api/v1/signals/{signal_id}")
```

**Expected:**
```python
response.status_code == 200
body = response.json()
assert body["signal_id"] == signal_id
assert body["signal"]["side"] == "LONG"
assert body["decision"]["decision"] == "PASS_MAIN"
assert len(body["filter_results"]) >= 3
assert body["telegram_messages"][0]["delivery_status"] in ["SENT", "FAILED"]
```

---

## TC-016: GET /signals/{signal_id} không tồn tại → 404

```python
response = client.get("/api/v1/signals/nonexistent-id")
assert response.status_code == 404
```

---

## FilterEngine Unit Tests (không cần DB)

> **Lưu ý:** FilterEngine dùng boolean gate, không phải scoring threshold.
> Decision dựa trên sự hiện diện của FAIL/WARN MEDIUM+, không dựa trên server_score >= threshold.
> server_score vẫn được tính và có thể assert để verify analytics — nhưng không là điều kiện routing.

```python
# tests/unit/test_filter_engine.py

from unittest.mock import MagicMock
from app.services.filter_engine import FilterEngine

def make_filter_engine(config_overrides=None):
    config = {
        "allowed_symbols": ["BTCUSDT"],
        "allowed_timeframes": ["1m","3m","5m","12m","15m"],
        "confidence_thresholds": {"5m": 0.78},
        "cooldown_minutes": {"5m": 10},
        "rr_min_base": 1.5,
        "rr_min_squeeze": 2.0,
        "duplicate_price_tolerance_pct": 0.2,
        "news_block_before_min": 15,
        "news_block_after_min": 30,
        # Không có main_score_threshold/warning_score_threshold
        # Boolean gate không cần score threshold
    }
    if config_overrides:
        config.update(config_overrides)

    mock_signal_repo = MagicMock()
    mock_signal_repo.find_recent_same_side.return_value = []
    mock_signal_repo.find_recent_similar.return_value = []

    mock_market_event_repo = MagicMock()
    mock_market_event_repo.find_active_around.return_value = []

    return FilterEngine(config, mock_signal_repo, mock_market_event_repo)

def make_signal(**overrides):
    base = {
        "signal_id": "test-001",
        "side": "LONG",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "price": 68250.5,
        "entry_price": 68250.5,
        "stop_loss": 67980.0,
        "take_profit": 68740.0,
        "risk_reward": 1.81,
        "indicator_confidence": 0.82,
        "signal_type": "LONG_V73",
        "regime": "WEAK_TREND_DOWN",
        "vol_regime": "TRENDING_LOW_VOL",
        "vol_ratio": 1.24,
    }
    base.update(overrides)
    return base

# Test 1: Happy path — không FAIL, không WARN MEDIUM+ → PASS_MAIN
def test_pass_main():
    engine = make_filter_engine()
    result = engine.run(make_signal())
    assert result.final_decision == "PASS_MAIN"
    assert result.route == "MAIN"
    assert 0.0 <= result.server_score <= 1.0  # tính được nhưng không dùng để route

# Test 2: Confidence too low → FAIL → REJECT
def test_reject_low_confidence():
    engine = make_filter_engine()
    result = engine.run(make_signal(indicator_confidence=0.75))
    assert result.final_decision == "REJECT"
    assert result.route == "NONE"
    fail_rules = [r.rule_code for r in result.filter_results if r.result == "FAIL"]
    assert "MIN_CONFIDENCE_BY_TF" in fail_rules

# Test 3: STRONG_TREND_DOWN + LONG → FAIL → REJECT
def test_reject_strong_downtrend_long():
    engine = make_filter_engine()
    result = engine.run(make_signal(regime="STRONG_TREND_DOWN"))
    assert result.final_decision == "REJECT"
    assert result.route == "NONE"

# Test 4: RANGING_HIGH_VOL → WARN MEDIUM → PASS_WARNING (không reject)
# Boolean gate key insight: RANGING_HIGH_VOL không làm REJECT, chỉ downgrade channel
def test_ranging_high_vol_routes_to_warning_not_reject():
    engine = make_filter_engine()
    result = engine.run(make_signal(vol_regime="RANGING_HIGH_VOL"))
    assert result.final_decision == "PASS_WARNING"  # WARN MEDIUM → warning
    assert result.route == "WARN"
    # server_score giảm vì -0.08 delta, nhưng không quyết định route
    warn_rules = [r.rule_code for r in result.filter_results if r.result == "WARN"]
    assert "VOLATILITY_WARNING" in warn_rules

# Test 5: Unsupported symbol → FAIL → REJECT
def test_reject_unsupported_symbol():
    engine = make_filter_engine()
    result = engine.run(make_signal(symbol="ETHUSDT"))
    assert result.final_decision == "REJECT"

# Test 6: Cooldown → WARN MEDIUM → PASS_WARNING (không phụ thuộc confidence cao hay thấp)
def test_cooldown_always_routes_to_warning():
    engine = make_filter_engine()
    engine.signal_repo.find_recent_same_side.return_value = [MagicMock()]
    # Dù confidence = 0.99, cooldown WARN MEDIUM vẫn downgrade
    result = engine.run(make_signal(indicator_confidence=0.99))
    assert result.final_decision == "PASS_WARNING"
    assert result.route == "WARN"

# Test 7: RR too low → FAIL → REJECT
def test_reject_low_rr():
    engine = make_filter_engine()
    result = engine.run(make_signal(risk_reward=1.2))
    assert result.final_decision == "REJECT"

# Test 8: Squeeze trade cần rr_min_squeeze=2.0
def test_squeeze_requires_higher_rr():
    engine = make_filter_engine()
    # rr=1.8 đủ cho base (>=1.5) nhưng không đủ cho squeeze (>=2.0)
    result = engine.run(make_signal(
        signal_type="SHORT_SQUEEZE", side="SHORT",
        entry_price=68910.0, stop_loss=69200.0,
        take_profit=68400.0, risk_reward=1.76
    ))
    assert result.final_decision == "REJECT"
    fail_rules = [r.rule_code for r in result.filter_results if r.result == "FAIL"]
    assert "MIN_RR_REQUIRED" in fail_rules

# Test 9: SQUEEZE_BUILDING (WARN LOW) không downgrade sang WARNING
# WARN LOW không đủ để route sang WARN channel
def test_squeeze_building_stays_main():
    engine = make_filter_engine()
    result = engine.run(make_signal(vol_regime="SQUEEZE_BUILDING"))
    assert result.final_decision == "PASS_MAIN"  # WARN LOW → vẫn MAIN
    assert result.route == "MAIN"

# Test 10: server_score được tính đúng (analytics check)
def test_server_score_calculated_for_analytics():
    engine = make_filter_engine()
    # RANGING_HIGH_VOL có score_delta=-0.08
    result = engine.run(make_signal(
        indicator_confidence=0.82,
        vol_regime="RANGING_HIGH_VOL"
    ))
    # server_score = 0.82 + (-0.08) = 0.74
    assert abs(result.server_score - 0.74) < 0.01
    # Nhưng decision là PASS_WARNING (WARN MEDIUM present), không phải REJECT
    assert result.final_decision == "PASS_WARNING"
```


## SignalNormalizer Unit Tests

```python
def test_normalize_long_calculates_rr():
    payload = TradingViewWebhookPayload(**make_payload())
    normalized = SignalNormalizer.normalize(payload)
    # risk = 68250.5 - 67980.0 = 270.5
    # reward = 68740.0 - 68250.5 = 489.5
    # rr = 489.5 / 270.5 ≈ 1.81
    assert abs(normalized["risk_reward"] - 1.81) < 0.01

def test_normalize_short_calculates_rr():
    payload_data = make_payload(signal="short")
    payload_data["metadata"]["entry"] = 68910.0
    payload_data["metadata"]["stop_loss"] = 69121.0
    payload_data["metadata"]["take_profit"] = 68277.0
    payload = TradingViewWebhookPayload(**payload_data)
    normalized = SignalNormalizer.normalize(payload)
    # risk = 69121 - 68910 = 211
    # reward = 68910 - 68277 = 633
    # rr ≈ 3.0
    assert abs(normalized["risk_reward"] - 3.0) < 0.1

def test_normalize_maps_side_to_uppercase():
    payload = TradingViewWebhookPayload(**make_payload(signal="long"))
    normalized = SignalNormalizer.normalize(payload)
    assert normalized["side"] == "LONG"

def test_normalize_rr_none_when_risk_zero():
    payload_data = make_payload()
    payload_data["metadata"]["stop_loss"] = 68250.5  # sl = entry → risk = 0
    payload = TradingViewWebhookPayload(**payload_data)
    normalized = SignalNormalizer.normalize(payload)
    assert normalized["risk_reward"] is None
```

---

## MessageRenderer Unit Tests

```python
def test_render_main_long_contains_key_info():
    signal = {"side": "LONG", "symbol": "BTCUSDT", "timeframe": "5m",
               "entry_price": 68250.5, "stop_loss": 67980.0, "take_profit": 68740.0,
               "risk_reward": 1.81, "indicator_confidence": 0.81,
               "signal_type": "LONG_V73", "regime": "WEAK_TREND_DOWN",
               "vol_regime": "TRENDING_LOW_VOL", "rsi": 31.2, "stoch_k": 12.8,
               "adx": 21.4, "atr_pct": 0.264, "source": "Bot_Webhook_v84"}
    text = MessageRenderer.render_main(signal, 0.84)
    assert "🟢" in text
    assert "LONG" in text
    assert "BTCUSDT" in text
    assert "5m" in text
    assert "81%" in text   # confidence
    assert "84%" in text   # score
    assert "expected_wr" not in text.lower()  # KHÔNG được có expected WR

def test_render_main_none_fields_show_na():
    signal = {"side": "LONG", "symbol": "BTCUSDT", "timeframe": "5m",
               "entry_price": 68250.5, "stop_loss": 67980.0, "take_profit": 68740.0,
               "risk_reward": None, "indicator_confidence": 0.80,
               "signal_type": None, "regime": None, "vol_regime": None,
               "rsi": None, "stoch_k": None, "adx": None, "atr_pct": None,
               "source": "Bot_Webhook_v84"}
    text = MessageRenderer.render_main(signal, 0.80)
    assert "N/A" in text   # None fields phải hiển thị N/A, không crash
```
