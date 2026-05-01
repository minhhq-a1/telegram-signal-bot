from __future__ import annotations

import pytest

from app.services.outcome_math import OutcomeMathError, compute_closed_outcome_metrics


def test_compute_long_tp_outcome_metrics():
    metrics = compute_closed_outcome_metrics(
        side="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        exit_price=110.0,
        close_reason="TP_HIT",
        max_favorable_price=112.0,
        max_adverse_price=98.0,
    )

    assert metrics["is_win"] is True
    assert metrics["pnl_pct"] == 10.0
    assert metrics["r_multiple"] == 2.0
    assert metrics["mfe_pct"] == 12.0
    assert metrics["mae_pct"] == -2.0


def test_compute_short_sl_outcome_metrics():
    metrics = compute_closed_outcome_metrics(
        side="SHORT",
        entry_price=100.0,
        stop_loss=105.0,
        exit_price=105.0,
        close_reason="SL_HIT",
        max_favorable_price=94.0,
        max_adverse_price=106.0,
    )

    assert metrics["is_win"] is False
    assert metrics["pnl_pct"] == -5.0
    assert metrics["r_multiple"] == -1.0
    assert metrics["mfe_pct"] == 6.0
    assert metrics["mae_pct"] == -6.0


def test_compute_manual_close_derives_win_from_r_multiple():
    metrics = compute_closed_outcome_metrics(
        side="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        exit_price=95.0,
        close_reason="MANUAL_CLOSE",
    )

    assert metrics["is_win"] is False
    assert metrics["r_multiple"] == -0.5


def test_invalid_risk_raises_invalid_outcome_values():
    with pytest.raises(OutcomeMathError) as exc_info:
        compute_closed_outcome_metrics(
            side="LONG",
            entry_price=100.0,
            stop_loss=100.0,
            exit_price=105.0,
            close_reason="TP_HIT",
        )

    assert exc_info.value.error_code == "INVALID_OUTCOME_VALUES"


def test_unknown_close_reason_raises_invalid_close_reason():
    with pytest.raises(OutcomeMathError) as exc_info:
        compute_closed_outcome_metrics(
            side="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            exit_price=105.0,
            close_reason="BAD_REASON",
        )

    assert exc_info.value.error_code == "INVALID_CLOSE_REASON"
