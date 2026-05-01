from __future__ import annotations

from typing import Any

_VALID_CLOSE_REASONS = {
    "TP_HIT",
    "SL_HIT",
    "MANUAL_CLOSE",
    "EXPIRED",
    "INVALID_SIGNAL",
    "UNKNOWN",
}


class OutcomeMathError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def compute_closed_outcome_metrics(
    *,
    side: str,
    entry_price: float,
    stop_loss: float,
    exit_price: float,
    close_reason: str,
    max_favorable_price: float | None = None,
    max_adverse_price: float | None = None,
) -> dict[str, Any]:
    normalized_reason = close_reason.upper()
    if normalized_reason not in _VALID_CLOSE_REASONS:
        raise OutcomeMathError("INVALID_CLOSE_REASON", f"Unsupported close_reason: {close_reason}")

    side_value = side.upper()
    if side_value == "LONG":
        risk = entry_price - stop_loss
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        r_multiple = (exit_price - entry_price) / risk if risk > 0 else None
        mfe_pct = _pct(max_favorable_price, entry_price, long_side=True)
        mae_pct = _pct(max_adverse_price, entry_price, long_side=True)
    elif side_value == "SHORT":
        risk = stop_loss - entry_price
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100
        r_multiple = (entry_price - exit_price) / risk if risk > 0 else None
        mfe_pct = _pct(max_favorable_price, entry_price, long_side=False)
        mae_pct = _pct(max_adverse_price, entry_price, long_side=False)
    else:
        raise OutcomeMathError("INVALID_OUTCOME_VALUES", f"Unsupported signal side: {side}")

    if entry_price <= 0 or stop_loss <= 0 or exit_price <= 0 or risk <= 0 or r_multiple is None:
        raise OutcomeMathError(
            "INVALID_OUTCOME_VALUES",
            "Cannot compute R multiple because risk is not positive",
        )

    if normalized_reason == "TP_HIT":
        is_win = True
    elif normalized_reason == "SL_HIT":
        is_win = False
    else:
        is_win = r_multiple > 0

    return {
        "close_reason": normalized_reason,
        "is_win": is_win,
        "pnl_pct": round(pnl_pct, 4),
        "r_multiple": round(r_multiple, 4),
        "mfe_pct": round(mfe_pct, 4) if mfe_pct is not None else None,
        "mae_pct": round(mae_pct, 4) if mae_pct is not None else None,
    }


def _pct(price: float | None, entry_price: float, *, long_side: bool) -> float | None:
    if price is None:
        return None
    if long_side:
        return ((price - entry_price) / entry_price) * 100
    return ((entry_price - price) / entry_price) * 100
