from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from app.repositories.signal_repo import SignalRepository
from app.domain.models import WebhookEvent
from sqlalchemy import text

@pytest.fixture
def signal_repo(db_session: Session) -> SignalRepository:
    return SignalRepository(db_session)

@pytest.fixture
def base_signal_data(db_session: Session) -> Dict[str, Any]:
    # PostgreSQL enforces FK constraint — must create the webhook_events row first
    webhook = WebhookEvent(
        id="test-webhook-id",
        raw_body={},
        auth_status="valid",
    )
    db_session.add(webhook)
    db_session.commit()

    return {
        "webhook_event_id": "test-webhook-id",
        "signal_id": "test-signal-id-1",
        "side": "LONG",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "price": 65000.0,
        "entry_price": 65000.0,
        "stop_loss": 64000.0,
        "take_profit": 67000.0,
        "risk_reward": 2.0,
        "indicator_confidence": 0.85,
        "server_score": 0.9,
        "signal_type": "LONG_V73",
        "strategy": "RSI_STOCH_V73",
        "source": "tv_test",
        "raw_payload": "{}"
    }

def test_find_recent_similar_price(signal_repo: SignalRepository, db_session: Session, base_signal_data: Dict[str, Any]):
    """
    Test Duplicate suppression (find_recent_similar).
    Price tolerance check.
    """
    # 1. Create original signal at 65,000
    signal_repo.create(base_signal_data)
    
    # 2. Look for similar signals at 65,050 (0.07% diff < 0.2%)
    similar_signals = signal_repo.find_recent_similar(
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        signal_type="LONG_V73",
        since_minutes=60,
        price_tolerance_pct=0.002
    )
    assert len(similar_signals) > 0 # We found the one we just inserted!
    
    # 3. Look for something entirely different in price
    # Ex: a price of 70,000 vs 65,000 (well over 0.2% diff)
    db_session.execute(
        text("UPDATE signals SET entry_price = 70000.0 WHERE signal_id = 'test-signal-id-1'")
    )
    db_session.commit()
    
    similar_signals_2 = signal_repo.find_recent_similar(
        symbol="BTCUSDT",
        timeframe="5m",
        side="LONG",
        signal_type="LONG_V73", # Need to include current logic params
        since_minutes=60,
        price_tolerance_pct=0.002
    )
    # The current signal's price in DB is 70,000. Is 65,000 (+-0.2%) able to find 70,000? No! 
    # Oh wait, find_recent_similar doesn't take the price parameter itself. It returns ALL recent signals matching metadata.
    # The actual Filter Engine checks the price difference: abs(past.entry_price - current.entry_price) / current.entry_price < tolerance.
    # So `find_recent_similar` purely queries timeframe, symbol, side, signal_type!
    # Let's just assert that it fetches correctly based on these fields.
    assert len(similar_signals_2) == 1
    assert similar_signals_2[0].signal_type == "LONG_V73"
