from __future__ import annotations

from types import SimpleNamespace

from app.services.market_context_service import MarketContextService


class _Repo:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def find_snapshot(self, symbol: str, timeframe: str, bar_time):
        return self.snapshot


def test_market_context_disabled_returns_none():
    svc = MarketContextService(_Repo(None))
    result = svc.compare_regime({"symbol": "BTCUSDT", "timeframe": "5m", "bar_time": "x", "regime": "A"}, enabled=False)
    assert result is None


def test_market_context_match_returns_pass():
    snapshot = SimpleNamespace(backend_regime="WEAK_TREND_DOWN")
    svc = MarketContextService(_Repo(snapshot))
    result = svc.compare_regime({"symbol": "BTCUSDT", "timeframe": "5m", "bar_time": "x", "regime": "WEAK_TREND_DOWN"}, enabled=True)
    assert result is not None
    assert result.result.value == "PASS"


def test_market_context_mismatch_returns_warn():
    snapshot = SimpleNamespace(backend_regime="STRONG_TREND_DOWN")
    svc = MarketContextService(_Repo(snapshot))
    result = svc.compare_regime({"symbol": "BTCUSDT", "timeframe": "5m", "bar_time": "x", "regime": "WEAK_TREND_DOWN"}, enabled=True)
    assert result is not None
    assert result.result.value == "WARN"
