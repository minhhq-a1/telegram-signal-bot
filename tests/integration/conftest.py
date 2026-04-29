from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db  # noqa: E402
from app.domain.models import Base  # noqa: E402
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


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(INTEGRATION_DATABASE_URL)
    Base.metadata.create_all(engine)
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
        Base.metadata.drop_all(engine)
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
            "strategy": "RSI_STOCH_V73",
            "regime": "WEAK_TREND_DOWN",
            "vol_regime": "TRENDING_LOW_VOL",
            "rsi": 31.2,
            "stoch_k": 12.8,
            "adx": 21.4,
            "atr": 180.3,
            "atr_pct": 0.264,
            "vol_ratio": 1.24,
            "bar_confirmed": True,
        },
    }


@pytest.fixture
def make_stored_signal(db_session):
    """Create a persisted Signal + SignalDecision row for integration testing."""
    created_ids: list = []

    def _mk(**overrides) -> Signal:
        import uuid
        from app.domain.models import Signal, SignalDecision

        sig = Signal(
            id=str(uuid.uuid4()),
            signal_id=f"test-{uuid.uuid4().hex[:8]}",
            source="Bot_Webhook_v84",
            symbol="BTCUSD",
            timeframe="15m",
            side="SHORT",
            price=74988.60,
            entry_price=74988.60,
            stop_loss=75429.33,
            take_profit=73886.79,
            risk_reward=2.5,
            indicator_confidence=0.90,
            raw_payload={
                "secret": "test",
                "signal": "short",
                "symbol": "BTCUSD",
                "timeframe": "15",
                "price": 74988.60,
                "source": "Bot_Webhook_v84",
                "confidence": 0.90,
                "metadata": {
                    "entry": 74988.60,
                    "stop_loss": 75429.33,
                    "take_profit": 73886.79,
                    "signal_type": overrides.get("signal_type", "SHORT_SQUEEZE"),
                    "strategy": overrides.get("strategy", "KELTNER_SQUEEZE"),
                    "squeeze_fired": overrides.get("squeeze_fired", 1),
                    "mom_direction": overrides.get("mom_direction", -1),
                    "vol_regime": overrides.get("vol_regime", "BREAKOUT_IMMINENT"),
                    "rsi": overrides.get("rsi", 37.5),
                    "rsi_slope": overrides.get("rsi_slope", -5.7),
                    "kc_position": overrides.get("kc_position", 0.31),
                    "atr_pct": overrides.get("atr_pct", 0.49),
                    "regime": overrides.get("regime", "WEAK_TREND_DOWN"),
                    "squeeze_bars": overrides.get("squeeze_bars", 6),
                    "stoch_k": overrides.get("stoch_k", 41.4),
                    "atr_percentile": overrides.get("atr_percentile", 78.0),
                    "adx": overrides.get("adx", 17.5),
                    "atr": overrides.get("atr", 367.28),
                    "bar_confirmed": True,
                    "stop_loss": 75429.33,
                    "take_profit": 73886.79,
                },
            },
        )
        for key, val in overrides.items():
            if hasattr(sig, key):
                setattr(sig, key, val)
        db_session.add(sig)
        db_session.add(SignalDecision(
            id=str(uuid.uuid4()),
            signal_row_id=sig.id,
            decision=overrides.get("original_decision", "PASS_MAIN"),
            decision_reason="seeded",
            telegram_route="MAIN",
        ))
        db_session.commit()
        created_ids.append(sig.id)
        return sig

    yield _mk
    db_session.query(Signal).filter(Signal.id.in_(created_ids)).delete(synchronize_session=False)
    db_session.commit()