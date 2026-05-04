"""
Market context rules: regime mismatch detection.
"""
from app.services.filter_rules.types import FilterResult
from app.services.market_context_service import MarketContextService


def check_market_context(signal: dict, config: dict, market_context_repo, results: list[FilterResult]) -> None:
    """
    V1.3: Market context regime mismatch check.
    Delegates to MarketContextService.compare_regime() for business logic.
    """
    market_config = config.get("market_context", {})
    enabled = bool(market_config.get("enabled", False))
    max_age = int(market_config.get("snapshot_max_age_minutes", 10))

    result = MarketContextService(market_context_repo).compare_regime(
        signal,
        enabled=enabled,
        snapshot_max_age_minutes=max_age,
    )

    if result is not None:
        results.append(result)
