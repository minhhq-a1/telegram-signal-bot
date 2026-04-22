# PostgreSQL Integration Tests — Design Spec

**Date:** 2026-04-22
**Author:** Ez02

---

## Goal

Migrate integration tests from SQLite in-memory to real PostgreSQL so that `CHECK` constraints, `TIMESTAMPTZ` semantics, and `JSONB` types are enforced — closing the gap between test and production behavior.

## Architecture

### Two-tier test strategy

| Tier | Engine | When runs | Marker |
|------|--------|-----------|--------|
| Unit tests (`tests/unit/`) | No DB / mock | Always | (none) |
| Integration tests (`tests/integration/`) | PostgreSQL | When `INTEGRATION_DATABASE_URL` is set | `@pytest.mark.integration` |

Integration tests are skipped (not failed) when `INTEGRATION_DATABASE_URL` is absent. This keeps local dev unblocked while CI always runs the full suite.

### Env var: `INTEGRATION_DATABASE_URL`

A separate env var from `DATABASE_URL` (production) to prevent accidental cross-wiring. Format: `postgresql+psycopg://user:pass@host:port/db`.

- **CI:** Set via GitHub Actions job env, pointing to the service container.
- **Local (optional):** Developer sets in `.env.test` or shell if they have a local PostgreSQL.

---

## Changes

### 1. `tests/integration/conftest.py`

**Replace** the SQLite `db_session` fixture with a PostgreSQL fixture:

```python
import os, pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from collections.abc import Generator
from app.domain.models import Base
from app.repositories.config_repo import ConfigRepository

INTEGRATION_DATABASE_URL = os.environ.get("INTEGRATION_DATABASE_URL")

def pytest_collection_modifyitems(config, items):
    if not INTEGRATION_DATABASE_URL:
        skip = pytest.mark.skip(reason="INTEGRATION_DATABASE_URL not set — skipping integration tests")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(INTEGRATION_DATABASE_URL)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
        ConfigRepository.reset_cache()
```

Key points:
- `pytest_collection_modifyitems` hook applies skip at collection time — no test body runs if URL absent.
- `Base.metadata.create_all` / `drop_all` per test function gives full schema isolation without needing transactions.
- `ConfigRepository.reset_cache()` preserved from previous fix.

### 2. `.github/workflows/ci.yml`

Add `postgres:16` service container and `INTEGRATION_DATABASE_URL` to the `test` job:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5

    env:
      INTEGRATION_DATABASE_URL: postgresql+psycopg://test_user:test_pass@localhost:5432/test_db

    steps:
      # (existing steps unchanged)
```

`docker-build` job unchanged — no PostgreSQL needed there.

### 3. `pytest.ini`

Register the `integration` marker to suppress PytestUnknownMarkWarning:

```ini
[pytest]
...
markers =
    integration: marks tests as requiring a live PostgreSQL database
```

(No test files need to add `@pytest.mark.integration` explicitly — the skip hook targets by file path `tests/integration/`.)

### 4. `.env.example`

Add documentation entry:

```
# Integration test database (optional — if set, integration tests run against real PostgreSQL)
# INTEGRATION_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/test_db
```

---

## What is NOT in scope

- Adding new test cases (separate sprint)
- Rate limiting webhook (separate task)
- Test coverage for analytics/notifier/renderer (separate task)

---

## Success criteria

1. `python -m pytest tests/unit/ -q` passes locally without any env vars set
2. `python -m pytest tests/integration/ -q` prints "skipped" for all integration tests when `INTEGRATION_DATABASE_URL` is not set
3. CI `test` job runs all integration tests against real PostgreSQL and passes
4. A `CHECK` constraint violation (e.g. invalid `side` value) raises an error in integration tests — demonstrating SQLite gap is closed
