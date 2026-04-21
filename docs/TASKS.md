# Task Breakdown — Signal Bot V1
<!-- AI Agent: Đây là danh sách task theo thứ tự dependency. Làm từ trên xuống. -->
<!-- Mỗi task có: mô tả rõ, file cần tạo/sửa, definition of done, và context references -->

## Thứ tự thực hiện

```
Phase 0: Scaffold
Phase 1: Core domain (enums, schemas, models)
Phase 2: Infrastructure (DB, config, logging)
Phase 3: Repositories
Phase 4: Services (normalizer, filter engine, notifier)
Phase 5: API layer
Phase 6: Integration + wiring
Phase 7: Tests
```

---

## PHASE 0 — Project Scaffold

### TASK-001: Tạo cấu trúc thư mục và requirements

**Files cần tạo:**
```
requirements.txt
.env.example
app/__init__.py
app/api/__init__.py
app/core/__init__.py
app/domain/__init__.py
app/repositories/__init__.py
app/services/__init__.py
app/main.py  (skeleton)
Dockerfile
docker-compose.yml
migrations/001_init.sql
```

**requirements.txt:**
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
psycopg[binary]==3.2.1
pydantic==2.9.2
pydantic-settings==2.5.2
httpx==0.27.2
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

**DoD:** `uvicorn app.main:app` chạy không lỗi, trả health check đơn giản.

---

## PHASE 1 — Core Domain

### TASK-002: Enums

**File:** `app/core/enums.py`

**Tạo các enums:**
- `SignalSide`: LONG, SHORT
- `DecisionType`: PASS_MAIN, PASS_WARNING, REJECT
- `TelegramRoute`: MAIN, WARN, NONE
- `RuleResult`: PASS, WARN, FAIL
- `RuleSeverity`: INFO, LOW, MEDIUM, HIGH, CRITICAL
- `DeliveryStatus`: PENDING, SENT, FAILED, SKIPPED
- `AuthStatus`: OK, INVALID_SECRET, MISSING

**Convention:** Tất cả là `str, Enum` để serialize thành JSON dễ dàng.

**DoD:** `from app.core.enums import SignalSide; SignalSide.LONG == "LONG"` → True

---

### TASK-003: Pydantic Schemas

**File:** `app/domain/schemas.py`

**Tạo:**
1. `SignalMetadata` — nested model cho `metadata` field
2. `TradingViewWebhookPayload` — main request schema với validators
3. `WebhookAcceptedResponse` — response schema
4. `ErrorResponse` — error response schema
5. `FilterResultSchema` — serialization schema cho filter results
6. `SignalDetailResponse` — response cho GET /signals/{id}

**Validators cần có:**
- `symbol`, `timeframe`, `source` không được empty
- `confidence` trong range [0.0, 1.0] (dùng `Field(ge=0.0, le=1.0)`)
- `signal` phải là `Literal["long", "short"]`

**Reference:** `docs/PAYLOAD_CONTRACT.md` section 2, 3, 4

**DoD:** Có thể parse sample JSON từ `docs/PAYLOAD_CONTRACT.md` không lỗi.

---

### TASK-004: SQLAlchemy ORM Models

**File:** `app/domain/models.py`

**Tạo ORM models cho 8 bảng:**
1. `WebhookEvent`
2. `Signal`
3. `SignalFilterResult`
4. `SignalDecision`
5. `TelegramMessage`
6. `SystemConfig`
7. `MarketEvent`
8. `SignalOutcome`

**Convention:**
- Tất cả inherit từ `Base` (từ `app/core/database.py`)
- `id: Mapped[str]` (UUID string, không dùng UUID type của SA)
- `created_at: Mapped[datetime]` với default `datetime.now(timezone.utc)`
- Numeric fields dùng `Mapped[float | None]` với `mapped_column(Numeric(18,8))`

**Reference:** `docs/DATABASE_SCHEMA.md` section 1–8

**DoD:** `Base.metadata.create_all(engine)` không lỗi.

---

## PHASE 2 — Infrastructure

### TASK-005: Config

**File:** `app/core/config.py`

**Tạo `Settings(BaseSettings)`:**
- Required: `database_url`, `tradingview_shared_secret`, `telegram_bot_token`, `telegram_main_chat_id`, `telegram_warn_chat_id`, `telegram_admin_chat_id`
- Optional with defaults: `app_env="dev"`, `app_port=8080`, `log_level="INFO"`, `enable_news_block=True`, `log_reject_to_admin=True`
- `model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)`
- Export singleton: `settings = Settings()`

**DoD:** `from app.core.config import settings; settings.app_env` không raise.

---

### TASK-006: Database

**File:** `app/core/database.py`

**Tạo:**
- `engine = create_engine(settings.database_url, pool_pre_ping=True)`
- `SessionLocal = sessionmaker(...)`
- `Base = DeclarativeBase()`
- `def get_db()` — FastAPI dependency, yield session, đóng sau request

**DoD:** `next(get_db())` trả Session object không lỗi (với DB đang chạy).

---

### TASK-007: Logging

**File:** `app/core/logging.py`

**Tạo structured logger:**
- Format: JSON với fields: `timestamp`, `level`, `event`, `signal_id` (nếu có), `message`
- Không log `secret` hoặc bất kỳ sensitive field nào
- Helper: `get_logger(name: str) -> logging.Logger`

**DoD:** Log ra JSON parseable, không có field `secret`.

---

### TASK-008: SQL Migration

**File:** `migrations/001_init.sql`

**Tạo đầy đủ DDL từ `docs/DATABASE_SCHEMA.md`:**
- 8 bảng với đúng constraints và CHECK clauses
- 6 indexes
- INSERT default `system_configs`

**DoD:** `psql $DATABASE_URL -f migrations/001_init.sql` chạy thành công, idempotent với `IF NOT EXISTS`.

---

## PHASE 3 — Repositories

### TASK-009: WebhookEventRepository

**File:** `app/repositories/webhook_event_repo.py`

**Methods:**
```python
def create(self, data: dict) -> WebhookEvent
def mark_auth_failure(self, id: str, reason: str) -> None
```

**DoD:** Unit test insert và đọc lại được.

---

### TASK-010: SignalRepository

**File:** `app/repositories/signal_repo.py`

**Methods:**
```python
def find_by_signal_id(self, signal_id: str) -> Signal | None
def create(self, data: dict) -> Signal
def find_recent_same_side(self, symbol: str, timeframe: str, side: str, since_minutes: int) -> list[Signal]
def find_recent_similar(self, symbol: str, timeframe: str, side: str, signal_type: str | None, since_minutes: int, price_tolerance_pct: float = 0.002) -> list[Signal]
```

**Lưu ý `find_recent_similar`:** Filter thêm điều kiện entry price gần giống (cho duplicate detection).

**DoD:** `find_by_signal_id` trả `None` cho signal chưa tồn tại, trả đúng object nếu đã có.

---

### TASK-011: Các Repository còn lại

**Files:**
- `app/repositories/filter_result_repo.py`
  - `bulk_insert(results: list[dict], signal_row_id: str) -> None`
- `app/repositories/decision_repo.py`
  - `create(data: dict) -> SignalDecision`
  - `find_by_signal_row_id(signal_row_id: str) -> SignalDecision | None`
- `app/repositories/telegram_repo.py`
  - `create(data: dict) -> TelegramMessage`
  - `mark_sent(id: str, telegram_message_id: str, sent_at: datetime) -> None`
  - `mark_failed(id: str, error: str) -> None`
- `app/repositories/config_repo.py`
  - `get_signal_bot_config() -> dict` (cache 30s với `functools.lru_cache` hoặc simple TTL)
- `app/repositories/market_event_repo.py`
  - `find_active_around(ts: datetime, before_min: int = 15, after_min: int = 30) -> list[MarketEvent]`

**DoD:** Mỗi repo có ít nhất 1 happy-path test.

---

## PHASE 4 — Services

### TASK-012: AuthService

**File:** `app/services/auth_service.py`

```python
class AuthService:
    @staticmethod
    def validate_secret(secret: str) -> bool:
        return secrets.compare_digest(secret, settings.tradingview_shared_secret)
```

**Lưu ý:** Dùng `secrets.compare_digest` để tránh timing attack.

**DoD:** `validate_secret("wrong")` → False, `validate_secret(correct)` → True.

---

### TASK-013: SignalNormalizer

**File:** `app/services/signal_normalizer.py`

**Input:** `TradingViewWebhookPayload`  
**Output:** `dict` với tất cả fields cần thiết để insert vào `signals` table

**Logic:**
- Map `signal: "long"` → `side: "LONG"`
- Tính `risk_reward`: LONG = (tp-entry)/(entry-sl), SHORT = (entry-tp)/(sl-entry)
- `risk_reward = None` nếu risk <= 0
- Map tất cả metadata fields
- `raw_payload = payload.model_dump(mode="json")`

**Reference:** `docs/ARCHITECTURE.md` section 3 — NormalizedSignal fields

**DoD:** Normalize sample payload LONG và SHORT, kiểm tra `risk_reward` tính đúng.

---

### TASK-014: FilterEngine ⭐ (task phức tạp nhất)

**File:** `app/services/filter_engine.py`

**Input:** `signal: dict` (output của normalizer), `config: dict`, `signal_repo`, `market_event_repo`  
**Output:** `FilterExecutionResult` dataclass

**Implement theo đúng thứ tự phases trong `docs/FILTER_RULES.md`:**

```
Phase 1 (hard, short-circuit): SYMBOL_ALLOWED, TIMEFRAME_ALLOWED, CONFIDENCE_RANGE_VALID, PRICE_VALID
Phase 2 (trade math): DIRECTION_SANITY_VALID → MIN_RR_REQUIRED
Phase 3a (hard rules → FAIL → REJECT): MIN_CONFIDENCE_BY_TF, REGIME_HARD_BLOCK, DUPLICATE_SUPPRESSION, NEWS_BLOCK
Phase 3b (advisory → WARN only): VOLATILITY_WARNING, COOLDOWN_ACTIVE, LOW_VOLUME_WARNING
Phase 4 (boolean routing):
    FAIL present        → REJECT
    WARN MEDIUM+ present → PASS_WARNING
    else                → PASS_MAIN
    server_score tính để log/analytics — KHÔNG dùng làm threshold
```

**Short-circuit:** Phase 1 fail → return reject ngay, không chạy tiếp.

**Helper method:**
```python
def _reject(self, results, score, reason) -> FilterExecutionResult
def _has_hard_fail(self, results) -> bool  # result == FAIL và severity in [HIGH, CRITICAL]
```

**Reference:** `docs/FILTER_RULES.md` toàn bộ

**DoD:** 8 test cases trong `TEST_CASES.md` đều pass.

---

### TASK-015: MessageRenderer

**File:** `app/services/message_renderer.py`

**Methods:**
```python
@staticmethod
def render_main(signal: dict, score: float) -> str

@staticmethod
def render_warning(signal: dict, score: float, reason: str) -> str

@staticmethod
def render_reject_admin(signal: dict, reason: str) -> str
```

**Format theo `docs/API_REFERENCE.md` section "Telegram Message Format"**

**Rules:**
- Số format với dấu phẩy ngàn: `68,250.50`
- Confidence/score format: `81%` (nhân 100, round, không decimal)
- Timezone: ICT (UTC+7)
- Không include `expected_wr` trong bất kỳ message nào
- `None` values hiển thị là `N/A`

**DoD:** Output render đúng format, không crash với `None` optional fields.

---

### TASK-016: TelegramNotifier

**File:** `app/services/telegram_notifier.py`

**Methods:**
```python
async def send_message(self, chat_id: str, text: str) -> dict
async def notify(self, route: str, text: str) -> tuple[str, dict | None]
    # route: "MAIN" | "WARN" | "ADMIN" | "NONE"
    # returns: (DeliveryStatus, telegram_response | None)
```

**Retry logic:**
- Max 3 attempts
- Backoff: 1s, 2s, 4s (`asyncio.sleep(2 ** attempt)`)
- Catch `httpx.TimeoutException`, `httpx.HTTPStatusError`
- Nếu hết retry → return `("FAILED", None)`, không raise

**DoD:** Mock Telegram API, test retry logic với fail lần 1 → success lần 2.

---

## PHASE 5 — API Layer

### TASK-017: HealthController

**File:** `app/api/health_controller.py`

```python
@router.get("/api/v1/health")
def get_health() -> HealthResponse:
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version}
```

**DoD:** `GET /api/v1/health` → 200 `{"status":"ok",...}`

---

### TASK-018: WebhookController ⭐ (endpoint chính)

**File:** `app/api/webhook_controller.py`

**Implement đúng flow theo `docs/ARCHITECTURE.md` section 2 — "Flow xử lý":**

```
1. validate auth → 401 nếu fail
2. idempotency check → return DUPLICATE nếu đã tồn tại
3. store raw webhook_event
4. normalize signal
5. validate direction sanity (trước khi insert signal)
6. insert signal
7. load config from DB
8. run filter engine
9. bulk insert filter_results
10. insert decision
11. db.commit()  <-- BẮT BUỘC COMMIT LẦN 1 TẠI ĐÂY (Persist trước khi ra public internet)
12. Phân luồng Notification:
    - Nếu PASS_MAIN / PASS_WARNING: Render message và send sang channel tương ứng.
    - Nếu REJECT và config['log_reject_to_admin'] == True: Render ADMIN message và send sang channel ADMIN.
13. insert telegram_message log
14. db.commit()  <-- COMMIT LẦN 2 (Cập nhật Telegram response)
15. return response
```

**Error handling:**
- Nếu DB fail sau bước 3: đã có raw log, trả 500
- Nếu Telegram fail: log error, không rollback DB, trả 200 (signal đã accept)

**DoD:** Test case TASK-018-T1: Valid LONG 5m → nhận 200 PASS_MAIN, DB có 4 rows (signal, filter_results×N, decision, telegram_message).

---

### TASK-019: SignalController

**File:** `app/api/signal_controller.py`

```python
@router.get("/api/v1/signals/{signal_id}")
def get_signal(signal_id: str, db: Session = Depends(get_db)) -> SignalDetailResponse:
```

Join signal + decision + filter_results + telegram_messages.  
Trả 404 nếu không tìm thấy.

**DoD:** GET signal vừa tạo → trả đúng decision và filter_results.

---

### TASK-020: Wire up main.py

**File:** `app/main.py`

```python
app = FastAPI(title="Telegram Signal Bot API", version=settings.app_version)
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(signal_router)
```

---

## PHASE 6 — Integration

### TASK-021: End-to-end smoke test

Chạy toàn bộ flow với real DB (test DB), không mock.

**Scenario:** POST valid LONG 5m payload → verify:
1. `webhook_events` có 1 row
2. `signals` có 1 row với đúng `risk_reward`
3. `signal_filter_results` có ≥ 5 rows
4. `signal_decisions` có 1 row với `decision = "PASS_MAIN"`
5. `telegram_messages` có 1 row với `delivery_status = "SENT"` (hoặc mock Telegram)

---

## PHASE 7 — Tests

### TASK-022: Unit tests

**Xem `docs/TEST_CASES.md`** để biết đầy đủ test cases.

**File structure:**
```
tests/
  unit/
    test_signal_normalizer.py
    test_filter_engine.py
    test_message_renderer.py
    test_auth_service.py
  integration/
    test_webhook_endpoint.py
    test_signal_repository.py
  conftest.py
```

---

## Dependency Map

```
TASK-001 (scaffold)
  └── TASK-002 (enums)
  └── TASK-005 (config)
  └── TASK-006 (database)
        └── TASK-003 (schemas)
        └── TASK-004 (models)
              └── TASK-008 (migration)
              └── TASK-009..011 (repositories)
                        └── TASK-012..016 (services)
                                    └── TASK-017..020 (API)
                                                └── TASK-021 (integration)
                                                └── TASK-022 (tests)
```

---

## Định nghĩa "Done" cho toàn dự án

- [ ] `GET /api/v1/health` → 200
- [ ] `POST /api/v1/webhooks/tradingview` với valid payload → 200 PASS_MAIN
- [ ] Secret sai → 401
- [ ] TF 30S → 400 UNSUPPORTED_TIMEFRAME
- [ ] Duplicate signal_id → 200 DUPLICATE (không insert thêm)
- [ ] Telegram message gửi thành công
- [ ] Toàn bộ audit trail trong DB trace được
- [ ] 8 test cases core trong TEST_CASES.md đều pass
