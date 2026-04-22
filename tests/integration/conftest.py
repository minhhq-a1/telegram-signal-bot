from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("tradingview_shared_secret", "test-secret")
os.environ.setdefault("database_url", "sqlite:///./test_bootstrap.db")
os.environ.setdefault("telegram_bot_token", "test-token")
os.environ.setdefault("telegram_main_chat_id", "main-chat")
os.environ.setdefault("telegram_warn_chat_id", "warn-chat")
os.environ.setdefault("telegram_admin_chat_id", "admin-chat")

from app.core.database import get_db  # noqa: E402
from app.domain.models import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.config_repo import ConfigRepository  # noqa: E402


@pytest.fixture
def db_session(tmp_path) -> Generator[Session, None, None]:
    db_path = tmp_path / "integration.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
        ConfigRepository.reset_cache()  # prevent cache leak between tests


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
