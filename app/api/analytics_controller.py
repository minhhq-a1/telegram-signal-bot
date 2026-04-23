from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, case, cast, Date, text

from app.core.database import get_db
from app.domain.models import Signal, SignalDecision, SignalFilterResult, TelegramMessage, WebhookEvent
from app.api.dependencies import require_dashboard_auth

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary")
def get_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Overview statistics: total signals, decision distribution, delivery rate.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total signals
    total_signals = db.execute(
        select(func.count(Signal.id)).where(Signal.created_at >= since)
    ).scalar() or 0

    # Decision distribution
    decision_rows = db.execute(
        select(
            SignalDecision.decision,
            func.count(SignalDecision.id).label("cnt"),
        )
        .join(Signal, Signal.id == SignalDecision.signal_row_id)
        .where(Signal.created_at >= since)
        .group_by(SignalDecision.decision)
    ).all()
    decisions = {row.decision: row.cnt for row in decision_rows}

    # Telegram delivery stats
    tg_rows = db.execute(
        select(
            TelegramMessage.delivery_status,
            func.count(TelegramMessage.id).label("cnt"),
        )
        .join(Signal, Signal.id == TelegramMessage.signal_row_id)
        .where(Signal.created_at >= since)
        .group_by(TelegramMessage.delivery_status)
    ).all()
    telegram = {row.delivery_status: row.cnt for row in tg_rows}

    # By side
    side_rows = db.execute(
        select(Signal.side, func.count(Signal.id).label("cnt"))
        .where(Signal.created_at >= since)
        .group_by(Signal.side)
    ).all()
    by_side = {row.side: row.cnt for row in side_rows}

    # By symbol
    symbol_rows = db.execute(
        select(Signal.symbol, func.count(Signal.id).label("cnt"))
        .where(Signal.created_at >= since)
        .group_by(Signal.symbol)
        .order_by(func.count(Signal.id).desc())
        .limit(10)
    ).all()
    by_symbol = {row.symbol: row.cnt for row in symbol_rows}

    # By timeframe
    tf_rows = db.execute(
        select(Signal.timeframe, func.count(Signal.id).label("cnt"))
        .where(Signal.created_at >= since)
        .group_by(Signal.timeframe)
        .order_by(func.count(Signal.id).desc())
    ).all()
    by_timeframe = {row.timeframe: row.cnt for row in tf_rows}

    # By strategy
    strat_rows = db.execute(
        select(Signal.strategy, func.count(Signal.id).label("cnt"))
        .where(Signal.created_at >= since)
        .group_by(Signal.strategy)
        .order_by(func.count(Signal.id).desc())
    ).all()
    by_strategy = {(row.strategy or "UNKNOWN"): row.cnt for row in strat_rows}

    # Avg confidence & avg server_score
    avg_row = db.execute(
        select(
            func.avg(Signal.indicator_confidence).label("avg_conf"),
            func.avg(Signal.server_score).label("avg_score"),
        ).where(Signal.created_at >= since)
    ).one()

    return {
        "period_days": days,
        "total_signals": total_signals,
        "decisions": decisions,
        "telegram_delivery": telegram,
        "by_side": by_side,
        "by_symbol": by_symbol,
        "by_timeframe": by_timeframe,
        "by_strategy": by_strategy,
        "avg_confidence": round(float(avg_row.avg_conf or 0), 4),
        "avg_server_score": round(float(avg_row.avg_score or 0), 4),
    }


@router.get("/signals/timeline")
def get_signal_timeline(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Recent signals with their decisions — for the timeline feed.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            Signal.id,
            Signal.signal_id,
            Signal.symbol,
            Signal.timeframe,
            Signal.side,
            Signal.entry_price,
            Signal.stop_loss,
            Signal.take_profit,
            Signal.risk_reward,
            Signal.indicator_confidence,
            Signal.server_score,
            Signal.signal_type,
            Signal.strategy,
            Signal.regime,
            Signal.vol_regime,
            Signal.rsi,
            Signal.adx,
            Signal.atr_pct,
            Signal.created_at,
            SignalDecision.decision,
            SignalDecision.decision_reason,
            SignalDecision.telegram_route,
        )
        .outerjoin(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .where(Signal.created_at >= since)
        .order_by(Signal.created_at.desc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()
    signals = []
    for r in rows:
        signals.append({
            "id": r.id,
            "signal_id": r.signal_id,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "side": r.side,
            "entry_price": float(r.entry_price) if r.entry_price else None,
            "stop_loss": float(r.stop_loss) if r.stop_loss else None,
            "take_profit": float(r.take_profit) if r.take_profit else None,
            "risk_reward": float(r.risk_reward) if r.risk_reward else None,
            "confidence": float(r.indicator_confidence) if r.indicator_confidence else None,
            "server_score": float(r.server_score) if r.server_score else None,
            "signal_type": r.signal_type,
            "strategy": r.strategy,
            "regime": r.regime,
            "vol_regime": r.vol_regime,
            "rsi": float(r.rsi) if r.rsi else None,
            "adx": float(r.adx) if r.adx else None,
            "atr_pct": float(r.atr_pct) if r.atr_pct else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "decision": r.decision,
            "decision_reason": r.decision_reason,
            "telegram_route": r.telegram_route,
        })

    return {"count": len(signals), "signals": signals}


@router.get("/filters/stats")
def get_filter_stats(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Filter rule performance: how often each rule triggers PASS/WARN/FAIL.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            SignalFilterResult.rule_code,
            SignalFilterResult.result,
            func.count(SignalFilterResult.id).label("cnt"),
        )
        .join(Signal, Signal.id == SignalFilterResult.signal_row_id)
        .where(Signal.created_at >= since)
        .group_by(SignalFilterResult.rule_code, SignalFilterResult.result)
        .order_by(SignalFilterResult.rule_code)
    )

    rows = db.execute(stmt).all()

    # Group by rule_code
    rules: dict[str, dict] = {}
    for r in rows:
        if r.rule_code not in rules:
            rules[r.rule_code] = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
        rules[r.rule_code][r.result] = r.cnt

    return {"period_days": days, "filter_rules": rules}


@router.get("/daily")
def get_daily_breakdown(
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Signals per day with decision breakdown — for charts.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            func.date(Signal.created_at).label("day"),
            SignalDecision.decision,
            func.count(Signal.id).label("cnt"),
        )
        .outerjoin(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .where(Signal.created_at >= since)
        .group_by("day", SignalDecision.decision)
        .order_by("day")
    )

    rows = db.execute(stmt).all()

    # Transform into {date: {decision: count}}
    daily: dict[str, dict] = {}
    for r in rows:
        # r.day is already a string in ISO format from func.date()
        day_str = str(r.day) if r.day else "unknown"
        if day_str not in daily:
            daily[day_str] = {"PASS_MAIN": 0, "PASS_WARNING": 0, "REJECT": 0, "DUPLICATE": 0}
        if r.decision:
            daily[day_str][r.decision] = r.cnt

    return {"period_days": days, "daily": daily}
