# Code Conventions — Signal Bot V1.1
<!-- AI Agent: Đọc file này trước khi viết bất kỳ code nào -->

## Nguyên tắc tổng quát

- **Simple but safe** — không over-engineer, không abstract sớm
- **Audit-first** — persist trước, notify sau. Không gửi Telegram trước khi DB commit
- **Fail fast** — validate sớm, return early, không để lỗi chạy sâu vào flow
- **Explicit over implicit** — enum thay string literal, typed dict thay **kwargs

---

## 1. Python style

```python
# ✅ Type hints bắt buộc cho mọi function signature
def find_by_signal_id(self, signal_id: str) -> Signal | None:

# ✅ Dùng | None thay Optional[] (Python 3.10+)
def get_config(key: str) -> dict | None:

# ✅ Dataclass cho internal models (không phải ORM, không phải Pydantic)
@dataclass
class FilterResult:
    rule_code: str
    rule_group: str
    result: str
    severity: str
    score_delta: float = 0.0
    details: dict | None = None

# ❌ Không dùng Any trừ khi thực sự cần
# ❌ Không dùng global state
# ❌ Không dùng mutable default argument
```

---

## 2. FastAPI patterns

```python
# ✅ Dependency injection cho DB session
@router.post("/api/v1/webhooks/tradingview")
async def receive_webhook(
    payload: TradingViewWebhookPayload,
    db: Session = Depends(get_db),
):

# ✅ HTTPException với error_code rõ ràng
raise HTTPException(
    status_code=401,
    detail={"status": "rejected", "error_code": "INVALID_SECRET", "message": "..."}
)

# ⚠️ Runtime hiện tại của repo đang dùng `detail="Invalid secret"` cho nhánh auth fail.
# Nếu muốn chuẩn hóa custom error body, cần sửa controller + tests + docs cùng lúc.

# ✅ Response model explicit
@router.post("...", response_model=WebhookAcceptedResponse, status_code=200)

# ❌ Không dùng request.body() trực tiếp — dùng Pydantic schema
# ❌ Không raise Exception thô — luôn dùng HTTPException hoặc custom exception
```

---

## 3. Repository pattern

Mỗi repository nhận `db: Session` qua constructor. Không dùng class method / static method cho DB operations.

```python
# ✅ Constructor injection
class SignalRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_signal_id(self, signal_id: str) -> Signal | None:
        stmt = select(Signal).where(Signal.signal_id == signal_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, data: dict) -> Signal:
        signal = Signal(**data)
        self.db.add(signal)
        self.db.flush()  # flush để lấy ID, chưa commit
        return signal

# ✅ Dùng SQLAlchemy 2.0 style (select(), không query())
from sqlalchemy import select
stmt = select(Signal).where(Signal.symbol == symbol).order_by(Signal.created_at.desc())
results = self.db.execute(stmt).scalars().all()

# ❌ Không dùng db.query() — SQLAlchemy 1.x style
# ❌ Không commit trong repository — commit ở controller/service layer
```

---

## 4. Service layer

```python
# ✅ Pure functions khi có thể (dễ test)
class SignalNormalizer:
    @staticmethod
    def normalize(payload: TradingViewWebhookPayload) -> dict:
        ...

# ✅ Inject dependencies qua constructor
class FilterEngine:
    def __init__(self, config: dict, signal_repo: SignalRepository, market_event_repo: MarketEventRepository | None = None):
        self.config = config
        self.signal_repo = signal_repo
        self.market_event_repo = market_event_repo

# ✅ Method run() trả dataclass, không raise exception cho business logic
def run(self, signal: dict) -> FilterExecutionResult:
    # Luôn trả result, kể cả REJECT — không throw exception
    ...
```

---

## 5. Error handling

```python
# ✅ Phân biệt rõ non-retryable vs retryable
# Non-retryable (4xx): invalid secret, invalid schema, unsupported TF
# Retryable (5xx): DB timeout, Telegram timeout

# ✅ Telegram retry với exponential backoff
async def send_with_retry(self, chat_id: str, text: str, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            return await self._send(chat_id, text)
        except httpx.TimeoutException:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s

# ✅ Luôn log signal_id trong mọi log entry liên quan đến signal
logger.info("signal_processed", extra={
    "signal_id": signal["signal_id"],
    "decision": result.final_decision,
    "server_score": result.server_score,
})

# ❌ Không dùng bare except:
# ❌ Không swallow exception mà không log
```

---

## 6. Database

```python
# ✅ Thứ tự persist (bắt buộc):
# 1. webhook_events  (ngay khi nhận, kể cả invalid)
# 2. signals
# 3. signal_filter_results  (bulk insert)
# 4. signal_decisions
# 5. telegram_messages  (sau khi send)

# ✅ Một transaction cho toàn bộ flow chính
# webhook_event + signal + filter_results + decision = 1 db.commit()
# telegram_messages = commit riêng sau khi send

# ✅ UUID generation ở Python layer, không rely on DB default
import uuid
signal_id_db = str(uuid.uuid4())

# ✅ Timestamp luôn UTC
from datetime import datetime, timezone
created_at = datetime.now(timezone.utc)
```

---

## 7. Config

```python
# ✅ Tất cả config từ env qua Pydantic Settings
class Settings(BaseSettings):
    tradingview_shared_secret: str  # REQUIRED — sẽ raise nếu thiếu
    telegram_bot_token: str         # REQUIRED

    model_config = SettingsConfigDict(env_file=".env")

# ✅ Business config (threshold, cooldown) từ DB, không từ env
# config_repo.get_signal_bot_config() → dict
# Cache 30s để tránh query mỗi request

# ❌ Không hardcode threshold trong code
# ❌ Không log secret dưới bất kỳ hình thức nào
```

---

## 8. Enums — dùng string enum để serialize dễ

```python
from enum import Enum

class SignalSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

# ✅ So sánh với enum value
if signal["side"] == SignalSide.LONG:  # OK
if signal["side"] == "LONG":           # OK nếu đã normalize

# ✅ Serialize tự động trong JSON response vì str Enum
```

---

## 9. Logging

```python
# ✅ Structured logging với extra fields
import logging
logger = logging.getLogger(__name__)

logger.info("webhook_received", extra={
    "signal_id": payload.signal_id,
    "symbol": payload.symbol,
    "timeframe": payload.timeframe,
})

# ✅ Log level conventions:
# DEBUG: raw payload details, individual filter results
# INFO:  signal received, decision made, telegram sent
# WARNING: PASS_WARNING signals, cooldown triggered
# ERROR: DB fail, Telegram fail sau retry hết

# ❌ Không log payload.secret dưới bất kỳ format nào
# ❌ Không dùng print() trong production code
```

---

## 10. Pydantic schemas

```python
# ✅ Validator cho string fields
@field_validator("symbol")
@classmethod
def normalize_symbol(cls, v: str) -> str:
    if not v or not v.strip():
        raise ValueError("must not be empty")
    return v.strip().upper()

@field_validator("timeframe")
@classmethod
def normalize_timeframe(cls, v: str) -> str:
    if not v or not v.strip():
        raise ValueError("must not be empty")
    return v.strip().lower()

@field_validator("source")
@classmethod
def normalize_source(cls, v: str) -> str:
    if not v or not v.strip():
        raise ValueError("must not be empty")
    return v.strip()

# ✅ Dùng model_dump(mode="json") để serialize cho DB storage
raw_payload = payload.model_dump(mode="json")

# ✅ Nested model cho metadata
class TradingViewWebhookPayload(BaseModel):
    metadata: SignalMetadata  # không dùng dict
```

---

## 11. Naming conventions

| Loại | Convention | Ví dụ |
|---|---|---|
| File | `snake_case.py` | `filter_engine.py` |
| Class | `PascalCase` | `FilterEngine`, `SignalRepository` |
| Method | `snake_case` | `find_by_signal_id()` |
| Constant | `UPPER_SNAKE` | `MAIN_SCORE_THRESHOLD` |
| DB column | `snake_case` | `signal_row_id`, `created_at` |
| Rule code | `UPPER_SNAKE` | `"MIN_RR_REQUIRED"` |
| Enum value | `UPPER_SNAKE` | `DecisionType.PASS_MAIN` |
| Env var | `UPPER_SNAKE` | `TRADINGVIEW_SHARED_SECRET` |

---

## 12. File không được tạo

```
❌ tests/  (tạo riêng theo TEST_CASES.md)
❌ alembic/ (dùng raw SQL migration thay)
❌ celery/  (V1.1 dùng FastAPI BackgroundTasks cho notify, chưa dùng queue)
❌ redis/   (V1.1 dùng DB cho cooldown/duplicate check; rate limit in-memory)
```
