# Skill: DB Schema
## Description
Implement `migrations/001_init.sql` hoặc `app/domain/models.py`.
Trigger khi user đề cập: migration, SQL, ORM models, database schema, CREATE TABLE, SQLAlchemy models, 8 bảng, init.sql.

## Instructions

Đọc `docs/DATABASE_SCHEMA.md` trước khi viết bất kỳ dòng SQL hoặc ORM nào.

---

### Nguyên tắc migration

```sql
-- Bắt buộc: idempotent
CREATE TABLE IF NOT EXISTS signals (...);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_tf_side_created_at ON signals(...);

-- Bắt buộc: extension UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Bắt buộc: default UUID
id UUID PRIMARY KEY DEFAULT gen_random_uuid()

-- Bắt buộc: timestamp UTC
created_at TIMESTAMP NOT NULL DEFAULT NOW()
```

### Thứ tự CREATE TABLE (FK dependency)

```
1. webhook_events       ← không có FK
2. signals              ← FK → webhook_events
3. signal_filter_results← FK → signals (CASCADE DELETE)
4. signal_decisions     ← FK → signals (CASCADE DELETE, UNIQUE)
5. telegram_messages    ← FK → signals (SET NULL on delete)
6. system_configs       ← không có FK
7. market_events        ← không có FK
8. signal_outcomes      ← FK → signals (CASCADE DELETE, UNIQUE)
```

### CHECK constraints bắt buộc

```sql
-- signals
side VARCHAR(8) NOT NULL CHECK (side IN ('LONG', 'SHORT'))

-- signal_filter_results
result VARCHAR(16) NOT NULL CHECK (result IN ('PASS', 'WARN', 'FAIL'))
severity VARCHAR(16) NOT NULL CHECK (severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))

-- signal_decisions
decision VARCHAR(32) NOT NULL CHECK (decision IN ('PASS_MAIN', 'PASS_WARNING', 'REJECT'))
telegram_route VARCHAR(32) CHECK (telegram_route IN ('MAIN', 'WARN', 'NONE'))

-- telegram_messages
delivery_status VARCHAR(32) NOT NULL CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'SKIPPED'))
```

### Default config INSERT — quan trọng

```sql
-- KHÔNG có main_score_threshold / warning_score_threshold
-- Đã bỏ khi chuyển sang boolean gate routing
INSERT INTO system_configs (config_key, config_value)
VALUES (
  'signal_bot_config',
  '{
    "allowed_symbols": ["BTCUSDT", "BTCUSD"],
    "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m"],
    "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74},
    "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25},
    "rr_min_base": 1.5,
    "rr_min_squeeze": 2.0,
    "duplicate_price_tolerance_pct": 0.2,
    "news_block_before_min": 15,
    "news_block_after_min": 30,
    "log_reject_to_admin": true
  }'::jsonb
)
ON CONFLICT (config_key) DO NOTHING;
```

### 6 Indexes bắt buộc

```sql
CREATE INDEX IF NOT EXISTS idx_signals_symbol_tf_side_created_at
  ON signals(symbol, timeframe, side, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_signal_type_created_at
  ON signals(signal_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_signal_id
  ON signals(signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_filter_results_signal_row_id
  ON signal_filter_results(signal_row_id);

CREATE INDEX IF NOT EXISTS idx_market_events_active_window
  ON market_events(is_active, start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_telegram_messages_signal_row_id
  ON telegram_messages(signal_row_id);
```

---

### SQLAlchemy ORM — conventions

```python
# Tất cả models inherit từ Base
from app.core.database import Base

class Signal(Base):
    __tablename__ = "signals"

    # ID là string UUID, không phải UUID type
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Numeric fields
    price: Mapped[float] = mapped_column(Numeric(18, 8))
    risk_reward: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    # JSON field
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
```

### Verify

```bash
psql $DATABASE_URL -f migrations/001_init.sql
# Chạy lại để test idempotency
psql $DATABASE_URL -f migrations/001_init.sql

psql $DATABASE_URL -c "\dt" | wc -l  # phải thấy 8+ bảng
psql $DATABASE_URL -c "SELECT config_key FROM system_configs;"
# Expected: signal_bot_config
```
