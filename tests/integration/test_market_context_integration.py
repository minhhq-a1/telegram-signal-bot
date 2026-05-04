from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.domain.models import MarketContextSnapshot
from app.repositories.market_context_repo import MarketContextRepository


def test_find_snapshot_returns_latest_at_or_before_bar_time(db_session):
    """Test that find_snapshot returns the most recent snapshot at or before bar_time within tolerance."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    # Insert snapshots around target_bar_time
    snapshots = [
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=15),  # Too old (outside 10min window)
            backend_regime="OLD_REGIME",
            source="test",
        ),
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=5),  # Within window, older
            backend_regime="OLDER_REGIME",
            source="test",
        ),
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=2),  # Within window, latest before target
            backend_regime="LATEST_REGIME",
            source="test",
        ),
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time + timedelta(minutes=2),  # After target (should be ignored)
            backend_regime="FUTURE_REGIME",
            source="test",
        ),
    ]

    for snapshot in snapshots:
        db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source="test", max_age_minutes=10)

    assert result is not None
    assert result.backend_regime == "LATEST_REGIME"
    assert result.bar_time == target_bar_time - timedelta(minutes=2)


def test_find_snapshot_ignores_snapshots_after_bar_time(db_session):
    """Test that snapshots newer than bar_time are ignored even if within symmetric window."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    # Only insert a snapshot after target_bar_time
    snapshot = MarketContextSnapshot(
        id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        timeframe="5m",
        bar_time=target_bar_time + timedelta(minutes=3),  # After target
        backend_regime="FUTURE_REGIME",
        source="test",
    )
    db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source="test", max_age_minutes=10)

    assert result is None


def test_find_snapshot_respects_tolerance_window(db_session):
    """Test that snapshots outside the tolerance window are ignored."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    # Insert snapshot just outside the 10-minute window
    snapshot = MarketContextSnapshot(
        id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        timeframe="5m",
        bar_time=target_bar_time - timedelta(minutes=11),  # Outside 10min window
        backend_regime="OLD_REGIME",
        source="test",
    )
    db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source="test", max_age_minutes=10)

    assert result is None


def test_find_snapshot_returns_exact_match_at_bar_time(db_session):
    """Test that a snapshot exactly at bar_time is returned."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    snapshot = MarketContextSnapshot(
        id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        timeframe="5m",
        bar_time=target_bar_time,  # Exact match
        backend_regime="EXACT_REGIME",
        source="test",
    )
    db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source="test", max_age_minutes=10)

    assert result is not None
    assert result.backend_regime == "EXACT_REGIME"
    assert result.bar_time == target_bar_time


def test_find_snapshot_filters_by_source_when_provided(db_session):
    """Test that source filtering works correctly."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    snapshots = [
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=2),
            backend_regime="SOURCE_A_REGIME",
            source="source_a",
        ),
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=2),
            backend_regime="SOURCE_B_REGIME",
            source="source_b",
        ),
    ]

    for snapshot in snapshots:
        db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source="source_a", max_age_minutes=10)

    assert result is not None
    assert result.backend_regime == "SOURCE_A_REGIME"
    assert result.source == "source_a"


def test_find_snapshot_without_source_filter(db_session):
    """Test that omitting source returns any matching snapshot."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    snapshot = MarketContextSnapshot(
        id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        timeframe="5m",
        bar_time=target_bar_time - timedelta(minutes=2),
        backend_regime="ANY_SOURCE_REGIME",
        source="any_source",
    )
    db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source=None, max_age_minutes=10)

    assert result is not None
    assert result.backend_regime == "ANY_SOURCE_REGIME"


def test_find_snapshot_filters_by_symbol_and_timeframe(db_session):
    """Test that symbol and timeframe filtering works correctly."""
    target_bar_time = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    snapshots = [
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=2),
            backend_regime="BTCUSDT_5M",
            source="test",
        ),
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="ETHUSDT",
            timeframe="5m",
            bar_time=target_bar_time - timedelta(minutes=2),
            backend_regime="ETHUSDT_5M",
            source="test",
        ),
        MarketContextSnapshot(
            id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            timeframe="15m",
            bar_time=target_bar_time - timedelta(minutes=2),
            backend_regime="BTCUSDT_15M",
            source="test",
        ),
    ]

    for snapshot in snapshots:
        db_session.add(snapshot)
    db_session.commit()

    repo = MarketContextRepository(db_session)
    result = repo.find_snapshot("BTCUSDT", "5m", target_bar_time, source="test", max_age_minutes=10)

    assert result is not None
    assert result.backend_regime == "BTCUSDT_5M"
    assert result.symbol == "BTCUSDT"
    assert result.timeframe == "5m"
