from __future__ import annotations

import os
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db  # noqa: E402
from app.core.migrations import apply_migrations_to_url  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.config_repo import ConfigRepository  # noqa: E402

INTEGRATION_DATABASE_URL = os.environ.get("INTEGRATION_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    """Skip all integration tests when INTEGRATION_DATABASE_URL is not set."""
    if not INTEGRATION_DATABASE_URL:
        skip_marker = pytest.mark.skip(
            reason="INTEGRATION_DATABASE_URL not set — set it to run integration tests against real PostgreSQL"
        )
        for item in items:
            if "tests/integration" in str(item.fspath):
                item.add_marker(skip_marker)


def _reset_db_with_migration(engine) -> None:
    # DROP SCHEMA clears all tables but the migration runner re-creates schema_migrations.
    # We also explicitly drop schema_migrations to ensure clean state in CI container reuse.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        # Ensure schema_migrations is also gone so migration runner re-creates it clean
        conn.execute(text("DROP TABLE IF EXISTS schema_migrations CASCADE"))
    apply_migrations_to_url(INTEGRATION_DATABASE_URL)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(INTEGRATION_DATABASE_URL)
    _reset_db_with_migration(engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        ConfigRepository.reset_cache()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def valid_payload() -> dict:
    return {
        "secret": "test-secret",
        "signal_id": "tv-btcusdt-5m-1713452400000-short-squeeze",
        "signal": "short",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "timestamp": "2026-04-18T15:30:00Z",
        "bar_time": "2026-04-18T15:30:00Z",
        "price": 68250.5,
        "source": "Bot_Webhook_v84",
        "confidence": 0.82,
        "metadata": {
            "entry": 68250.5,
            "stop_loss": 68650.0,
            "take_profit": 67000.0,
            "signal_type": "SHORT_SQUEEZE",
            "strategy": "KELTNER_SQUEEZE",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "BREAKOUT_IMMINENT",
            "squeeze_fired": 1,
            "mom_direction": -1,
            "rsi": 45.0,
            "rsi_slope": -5.0,
            "kc_position": 0.30,
            "atr_pct": 0.264,
            "atr_percentile": 65.0,
            "adx": 21.4,
            "atr": 180.3,
            "stoch_k": 12.8,
            "vol_ratio": 1.24,
            "bar_confirmed": True,
        },
    }
