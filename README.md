# Telegram Signal Bot V1.3

> **Mục tiêu:** Nhận alert từ TradingView, lọc tín hiệu 2 lớp, gửi signal tham khảo lên Telegram.  
> **Không** auto-trade. **Không** quản lý lệnh. Chỉ là **signal assistant**.

---

## Tổng quan hệ thống

```
TradingView (Pine Script v8.4)
    │  HTTPS POST JSON
    ▼
Webhook API  ──► Request Validation ──► Signal Normalizer
                                              │
                                        Filter Engine
                                        (Boolean Gate)
                                              │
                                       Decision Engine
                                PASS_MAIN / PASS_WARNING / REJECT / DUPLICATE
                                              │
                              ┌───────────────┴────────────────┐
                         PostgreSQL                      Telegram Bot
                  (audit trail first)            Main / Warn / Admin channel
```

---

## Phạm vi V1.3

| Trong phạm vi | Ngoài phạm vi |
|---|---|
| Nhận webhook TradingView | Auto trade |
| Lọc tín hiệu server-side | Position sizing tự động |
| Gửi Telegram notification | Auto trading dashboard |
| Lưu audit trail đầy đủ | Multi-user / multi-tenant |
| Dashboard/analytics/reverify/config admin/calibration proposals | Machine learning scoring |
| Outcome tracking + calibration/replay support | Position management |

---

## Tech stack

| Thành phần | Công nghệ |
|---|---|
| Backend API | Python 3.12 + FastAPI |
| Database | PostgreSQL 16 |
| HTTP Client | httpx (async) |
| Validation | Pydantic v2 |
| Deployment | Docker + Nginx (HTTPS bắt buộc) |
| Rate limiting | slowapi in-memory per-IP limit |

---

## Cấu trúc thư mục

```
app/
├── api/
│   ├── health_controller.py
│   ├── webhook_controller.py
│   ├── signal_controller.py
│   ├── analytics_controller.py
│   └── rate_limiter.py
├── core/
│   ├── config.py           # Pydantic settings từ .env
│   ├── enums.py            # SignalSide, DecisionType, RuleResult, etc.
│   ├── logging.py          # Structured logging
│   └── database.py         # SQLAlchemy engine + session
├── domain/
│   ├── schemas.py          # Pydantic request/response models
│   └── models.py           # SQLAlchemy ORM models
├── repositories/
│   ├── webhook_event_repo.py
│   ├── signal_repo.py
│   ├── filter_result_repo.py
│   ├── decision_repo.py
│   ├── telegram_repo.py
│   ├── config_repo.py
│   └── market_event_repo.py
├── services/
│   ├── auth_service.py
│   ├── signal_normalizer.py
│   ├── filter_engine.py    # Core: boolean gate routing
│   ├── strategy_validator.py
│   ├── rescoring_engine.py
│   ├── message_renderer.py
│   └── telegram_notifier.py
└── main.py
docs/
├── ARCHITECTURE.md         # Kiến trúc chi tiết
├── PAYLOAD_CONTRACT.md     # Payload spec TradingView ↔ Bot
├── FILTER_RULES.md         # Rule engine + boolean gate logic
├── DATABASE_SCHEMA.md      # DDL + schema reference
├── API_REFERENCE.md        # Endpoint docs
├── DEPLOYMENT.md           # Setup + checklist
├── DB_MIGRATION_RUNBOOK.md # Migration/versioning runbook
├── BACKUP_RECOVERY_RUNBOOK.md # Backup/restore/restore-drill guide
├── CONVENTIONS.md          # Coding conventions cho AI agent
├── VERSION_HISTORY.md      # Product history V1.0 → V1.3
├── RELEASE_V13_HANDOFF.md  # V1.3 release handoff
├── POST_V13_BACKLOG.md     # Post-V1.3 deploy backlog
├── TASKS.md                # Legacy V1 task breakdown + dependency order
├── TEST_CASES.md           # Test cases với input/output
├── QA_STRATEGY.md          # Acceptance criteria + QA checklist
├── CURSOR_CONTEXT.md       # Context tổng hợp cho AI assistant
├── PROJECT_INSTRUCTIONS.md # Claude.ai Projects instructions
└── examples/               # Sample JSON payloads
migrations/                  # Raw SQL migrations 001 → 010
.env.example
requirements.txt
Dockerfile
docker-compose.yml
README.md               # File này
AGENTS.md
GEMINI.md
```

---

## Quick Start (local dev)

### 1. Clone và chuẩn bị môi trường

```bash
cp .env.example .env
# Điền secret Telegram / TradingView trong .env
```

### 2. Khởi động PostgreSQL local

Local standard của repo này:
- app chạy trên host bằng `uvicorn`
- database chạy bằng Docker Compose
- `.env` dùng `localhost`
- nếu chạy cả app trong Compose, `docker-compose.yml` sẽ tự override `DATABASE_URL` sang host `db`

```bash
docker compose up -d db
```

### 3. Migration local

Repo hiện dùng **raw SQL versioned flow** với runner chính thức:

```bash
python3 scripts/db/migrate.py apply
```

Kiểm tra trạng thái migration:

```bash
python3 scripts/db/migrate.py status
```

Chi tiết xem thêm:
- `docs/DB_MIGRATION_RUNBOOK.md`
- `docs/BACKUP_RECOVERY_RUNBOOK.md`

### 4. Cài dependencies

```bash
# Cài đặt (khuyến nghị dùng venv)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Khởi chạy App
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 6. Test thử Webhook (Smoke Test)

Sử dụng lệnh `curl` sau để bắn một tín hiệu giả lập từ TradingView:

```bash
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
-H "Content-Type: application/json" \
-d '{
  "secret": "your_secret_here",
  "signal_id": "test-manual-001",
  "signal": "long",
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "price": 65000.0,
  "source": "Manual_Test",
  "confidence": 0.9,
  "metadata": {
    "entry": 65000.0,
    "stop_loss": 64500.0,
    "take_profit": 66500.0,
    "signal_type": "LONG_V73"
  }
}'
```


### 8. Chạy test

```bash
python3 -m pytest -q
```

### 9. Chạy full stack bằng Compose (optional)

```bash
docker compose up --build
```

Compose mode vẫn dùng cùng DB schema, nhưng service `app` sẽ tự override `DATABASE_URL` sang `db:5432`.

---

## Runtime Behavior

- `webhook_events` được lưu trước để giữ audit trail, kể cả khi secret sai.
- `signal_id` là idempotency key. Nếu trùng, API trả `200` với `decision="DUPLICATE"`.
- Business records được `db.commit()` trước khi gọi Telegram.
- `server_score` vẫn được tính và lưu DB để analytics, nhưng không dùng để route.
- Invalid JSON và invalid schema đều được audit vào `webhook_events` trước khi reject.
- Payload sai schema hoặc sai format datetime hiện trả `400 INVALID_SCHEMA`; malformed JSON trả `400 INVALID_JSON`.

### Boolean routing

```text
FAIL present          -> REJECT
WARN MEDIUM+ present  -> PASS_WARNING
else                  -> PASS_MAIN
```

### Preview Tin nhắn Telegram

```text
AI TRADING BOT
🟢 BTCUSDT LONG | 5m
Entry: 65,000.00
SL: 64,500.00
TP: 66,500.00
RR: 3.00
Conf: 90% | Score: 90%

Status: PASSED ✅
Time: 15:39 ICT
Source: TradingView_Alert
```


---

## Nguồn tín hiệu

Bot nhận alert từ **TradingView indicator Bot Webhook v8.4 [BTC]**:

- Pine Script gửi JSON webhook khi `longSignal` hoặc `shortSignal`
- Chỉ gửi khi `barstate.isconfirmed` (tránh repainting)
- Confidence tối thiểu: 70% (configurable tại indicator)
- Indicator có thể phát nhiều timeframe, nhưng backend V1.3 chỉ accept whitelist runtime

**Lưu ý quan trọng:**
- Indicator confidence là **heuristic score**, không phải xác suất thắng thực
- Bot áp dụng layer 2 filtering để giảm noise thêm
- Symbol whitelist V1.3: `BTCUSDT`, `BTCUSD`
- Timeframe whitelist V1.3: `1m`, `3m`, `5m`, `12m`, `15m`, `30m`, `1h`
- Các TF như `30S`, `45S`, `2m`, `4m`, `6m–11m`, `13m–20m`, `4h`, `1d` không nằm trong backend whitelist runtime

---

## Kênh Telegram

| Kênh | Loại tín hiệu |
|---|---|
| `MAIN_CHAT` | `PASS_MAIN` — tín hiệu đã qua toàn bộ filter |
| `WARN_CHAT` | `PASS_WARNING` — tín hiệu có cảnh báo nhẹ |
| `ADMIN_CHAT` | `REJECT` summary + lỗi hệ thống + debug |

---

## Lịch trình pilot

> Chạy paper trading **2–4 tuần** trước khi dùng live.

**Tuần 1–2:** Bật `3m`, `5m`, `15m`  
**Tuần 3–4:** Đánh giá, cân nhắc thêm `1m`, `12m`

---

## Tài liệu liên quan

- [ARCHITECTURE.md](./docs/ARCHITECTURE.md) — Kiến trúc và data flow chi tiết
- [PAYLOAD_CONTRACT.md](./docs/PAYLOAD_CONTRACT.md) — Spec payload TradingView
- [FILTER_RULES.md](./docs/FILTER_RULES.md) — Rule engine + boolean gate logic
- [DATABASE_SCHEMA.md](./docs/DATABASE_SCHEMA.md) — Schema PostgreSQL
- [API_REFERENCE.md](./docs/API_REFERENCE.md) — Endpoint reference
- [DEPLOYMENT.md](./docs/DEPLOYMENT.md) — Hướng dẫn triển khai
- [GITHUB_CICD.md](./docs/GITHUB_CICD.md) — GitHub Actions CI/CD
- [QA_STRATEGY.md](./docs/QA_STRATEGY.md) — Acceptance criteria + QA checklist
- [TASKS.md](./docs/TASKS.md) — Task breakdown cho AI agent
- [PROMPTS.md](./docs/PROMPTS.md) — 22 prompt theo lifecycle dự án
- [VERSION_HISTORY.md](./docs/VERSION_HISTORY.md) — Lịch sử V1.0 → V1.3
- [RELEASE_V13_HANDOFF.md](./docs/RELEASE_V13_HANDOFF.md) — V1.3 release handoff
- [POST_V13_BACKLOG.md](./docs/POST_V13_BACKLOG.md) — Post-V1.3 deploy backlog
- [CURSOR_CONTEXT.md](./docs/CURSOR_CONTEXT.md) — Context tổng hợp cho AI assistant


## Verify Commands

```bash
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration -q
python3 -m pytest -q
bash scripts/smoke_local.sh
```
