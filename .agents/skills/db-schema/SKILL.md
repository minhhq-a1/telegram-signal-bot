---
name: db-schema
description: "Implement or update database migrations and SQLAlchemy ORM models for the signal bot schema."
---

# Skill: DB Schema
## Description
Implement hoặc sửa `migrations/001_init.sql`, follow-up migrations, hoặc `app/domain/models.py`.
Trigger khi user đề cập: migration, SQL, ORM models, database schema, CREATE TABLE, SQLAlchemy models, init.sql.

## Instructions

Đọc `docs/DATABASE_SCHEMA.md`, `migrations/001_init.sql`, và `app/domain/models.py` trước khi viết SQL/ORM.

---

### Nguyên tắc hiện tại

- UUID generate ở Python layer: `str(uuid.uuid4())`.
- Primary keys hiện tại là `VARCHAR(36)`, không phải PostgreSQL `UUID DEFAULT gen_random_uuid()`.
- SQLAlchemy dùng 2.0 style: `select()`, không dùng `db.query()`.
- Timestamp dùng timezone-aware: Python `datetime.now(timezone.utc)` và SQL `TIMESTAMPTZ DEFAULT NOW()`.
- Migration phải idempotent: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ON CONFLICT DO NOTHING`.
- Raw migrations, không dùng Alembic.

### Thứ tự CREATE TABLE (FK dependency)

```
1. webhook_events        ← không có FK
2. signals               ← FK → webhook_events
3. signal_filter_results ← FK → signals (CASCADE DELETE)
4. signal_decisions      ← FK → signals (CASCADE DELETE, UNIQUE)
5. telegram_messages     ← FK → signals (SET NULL on delete)
6. system_configs        ← không có FK
7. market_events         ← không có FK
8. signal_outcomes       ← FK → signals (CASCADE DELETE, UNIQUE)
```

Follow-up migration hiện có:

```
003_v11_upgrade.sql → signal_reverify_results và V1.1 related indexes/columns
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
telegram_route VARCHAR(32) CHECK (telegram_route IN ('MAIN', 'WARN', 'ADMIN', 'NONE'))

-- telegram_messages
delivery_status VARCHAR(32) NOT NULL CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'SKIPPED'))
```

### Default config INSERT — current shape

Không có `main_score_threshold` / `warning_score_threshold`; routing là boolean gate.

```sql
INSERT INTO system_configs (id, config_key, config_value)
VALUES (
  'default-config-001',
  'signal_bot_config',
  '{
    "allowed_symbols": ["BTCUSDT", "BTCUSD"],
    "allowed_timeframes": ["1m", "3m", "5m", "12m", "15m", "30m", "1h"],
    "confidence_thresholds": {"1m": 0.82, "3m": 0.80, "5m": 0.78, "12m": 0.76, "15m": 0.74, "30m": 0.72, "1h": 0.70},
    "cooldown_minutes": {"1m": 5, "3m": 8, "5m": 10, "12m": 20, "15m": 25, "30m": 45, "1h": 90},
    "rr_min_base": 1.5,
    "rr_min_squeeze": 2.0,
    "duplicate_price_tolerance_pct": 0.002,
    "enable_news_block": true,
    "news_block_before_min": 15,
    "news_block_after_min": 30,
    "log_reject_to_admin": true
  }'::jsonb
)
ON CONFLICT (config_key) DO NOTHING;
```

### Indexes trong `001_init.sql`

```sql
CREATE INDEX IF NOT EXISTS idx_signals_symbol_tf_side_created_at
  ON signals(symbol, timeframe, side, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_strategy_created_at
  ON signals(strategy, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_signal_id
  ON signals(signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_filter_results_signal_row_id
  ON signal_filter_results(signal_row_id);

CREATE INDEX IF NOT EXISTS idx_market_events_time_window
  ON market_events(start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_telegram_messages_signal_row_id
  ON telegram_messages(signal_row_id);
```

### ORM conventions

```python
from datetime import datetime, timezone
from sqlalchemy import DateTime, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    price: Mapped[float] = mapped_column(Numeric(18, 8))
    risk_reward: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

### Market events current schema

`market_events` hiện dùng:

```sql
impact VARCHAR(16) NOT NULL -- HIGH | MEDIUM | LOW
```

Không dùng `impact_level` hoặc `is_active` trong model hiện tại. Query news block filter dùng `impact='HIGH'` và overlap `start_time/end_time`.

### Verify

```bash
rtk psql "$DATABASE_URL" -f migrations/001_init.sql
rtk psql "$DATABASE_URL" -f migrations/001_init.sql  # idempotency
rtk python -m pytest tests/integration/test_ci_migration_fixture.py -v
```
