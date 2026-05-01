from __future__ import annotations

from datetime import datetime, timezone, timedelta
from io import StringIO
import csv

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import select, func, case, cast, Date, text

from app.core.database import get_db
from app.domain.models import Signal, SignalDecision, SignalFilterResult, SignalOutcome, TelegramMessage, WebhookEvent
from app.api.dependencies import require_dashboard_auth
from app.core.config import settings
from app.repositories.config_repo import ConfigRepository
from app.services.reject_codes import rule_code_to_reject_code

_ALLOWED_GROUP_BY = frozenset(["signal_type", "reject_code"])
_ALLOWED_OUTCOME_GROUP_BY = frozenset([
    "timeframe", "signal_type", "strategy", "side", "decision", "telegram_route", "regime", "vol_regime"
])

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/outcomes/summary")
def get_outcome_summary(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    totals = db.execute(
        select(
            func.sum(case((SignalOutcome.outcome_status == "CLOSED", 1), else_=0)).label("closed_count"),
            func.sum(case((SignalOutcome.outcome_status == "OPEN", 1), else_=0)).label("open_count"),
            func.sum(case((SignalOutcome.outcome_status == "CLOSED", case((SignalOutcome.is_win.is_(True), 1), else_=0)), else_=0)).label("win_count"),
            func.avg(case((SignalOutcome.outcome_status == "CLOSED", SignalOutcome.r_multiple), else_=None)).label("avg_r"),
            func.sum(case((SignalOutcome.outcome_status == "CLOSED", SignalOutcome.r_multiple), else_=0)).label("total_r"),
            func.avg(case((SignalOutcome.outcome_status == "CLOSED", SignalOutcome.pnl_pct), else_=None)).label("avg_pnl"),
        )
        .join(Signal, Signal.id == SignalOutcome.signal_row_id)
        .where(Signal.created_at >= since)
    ).one()

    closed_outcomes = int(totals.closed_count or 0)
    open_outcomes = int(totals.open_count or 0)
    win_count = int(totals.win_count or 0)

    by_decision_rows = db.execute(
        select(
            SignalDecision.decision,
            func.count(SignalOutcome.id).label("cnt"),
            func.avg(SignalOutcome.r_multiple).label("avg_r"),
            func.sum(case((SignalOutcome.is_win.is_(True), 1), else_=0)).label("wins"),
        )
        .join(Signal, Signal.id == SignalDecision.signal_row_id)
        .join(SignalOutcome, SignalOutcome.signal_row_id == Signal.id)
        .where(Signal.created_at >= since, SignalOutcome.outcome_status == "CLOSED")
        .group_by(SignalDecision.decision)
    ).all()

    by_decision: dict[str, dict] = {}
    for row in by_decision_rows:
        count = int(row.cnt or 0)
        wins = int(row.wins or 0)
        by_decision[row.decision] = {
            "count": count,
            "win_rate": round((wins / count), 4) if count else 0.0,
            "avg_r": round(float(row.avg_r or 0), 4),
        }

    return {
        "period_days": days,
        "closed_outcomes": closed_outcomes,
        "open_outcomes": open_outcomes,
        "win_rate": round((win_count / closed_outcomes), 4) if closed_outcomes else 0.0,
        "avg_r_multiple": round(float(totals.avg_r or 0), 4),
        "median_r_multiple": 0.0,
        "total_r_multiple": round(float(totals.total_r or 0), 4),
        "avg_pnl_pct": round(float(totals.avg_pnl or 0), 4),
        "by_decision": by_decision,
    }


@router.get("/outcomes/by-bucket")
def get_outcome_buckets(
    days: int = Query(30, ge=1, le=90),
    group_by: str = Query("timeframe,signal_type"),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    tokens = [t.strip() for t in group_by.split(",") if t.strip()]
    if not tokens or any(t not in _ALLOWED_OUTCOME_GROUP_BY for t in tokens):
        return Response(status_code=400, content='{"error_code":"INVALID_GROUP_BY","message":"Invalid outcome group_by"}', media_type="application/json")

    column_map = {
        "timeframe": Signal.timeframe,
        "signal_type": Signal.signal_type,
        "strategy": Signal.strategy,
        "side": Signal.side,
        "decision": SignalDecision.decision,
        "telegram_route": SignalDecision.telegram_route,
        "regime": Signal.regime,
        "vol_regime": Signal.vol_regime,
    }
    select_cols = [column_map[t].label(t) for t in tokens]

    rows = db.execute(
        select(
            *select_cols,
            func.count(SignalOutcome.id).label("count"),
            func.avg(SignalOutcome.r_multiple).label("avg_r_multiple"),
            func.sum(case((SignalOutcome.is_win.is_(True), 1), else_=0)).label("wins"),
        )
        .join(Signal, Signal.id == SignalOutcome.signal_row_id)
        .join(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .where(Signal.created_at >= since, SignalOutcome.outcome_status == "CLOSED")
        .group_by(*select_cols)
        .order_by(func.count(SignalOutcome.id).desc())
    ).all()

    buckets = []
    for row in rows:
        count = int(row.count or 0)
        item = {token: getattr(row, token) for token in tokens}
        item.update({
            "count": count,
            "win_rate": round((int(row.wins or 0) / count), 4) if count else 0.0,
            "avg_r_multiple": round(float(row.avg_r_multiple or 0), 4),
        })
        buckets.append(item)

    return {"period_days": days, "group_by": tokens, "buckets": buckets}


@router.get("/outcomes/rules")
def get_outcome_rules(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(
            SignalFilterResult.rule_code,
            SignalFilterResult.result,
            SignalFilterResult.severity,
            func.count(SignalFilterResult.id).label("signals"),
            func.count(SignalOutcome.id).label("closed_outcomes"),
            func.sum(case((SignalOutcome.is_win.is_(True), 1), else_=0)).label("wins"),
            func.avg(SignalOutcome.r_multiple).label("avg_r_multiple"),
        )
        .join(Signal, Signal.id == SignalFilterResult.signal_row_id)
        .outerjoin(
            SignalOutcome,
            (SignalOutcome.signal_row_id == Signal.id) & (SignalOutcome.outcome_status == "CLOSED"),
        )
        .where(Signal.created_at >= since)
        .group_by(SignalFilterResult.rule_code, SignalFilterResult.result, SignalFilterResult.severity)
        .order_by(SignalFilterResult.rule_code)
    ).all()

    rules = []
    for row in rows:
        closed = int(row.closed_outcomes or 0)
        rules.append({
            "rule_code": row.rule_code,
            "result": row.result,
            "severity": row.severity,
            "signals": int(row.signals or 0),
            "closed_outcomes": closed,
            "win_rate": round((int(row.wins or 0) / closed), 4) if closed else 0.0,
            "avg_r_multiple": round(float(row.avg_r_multiple or 0), 4),
        })
    return {"period_days": days, "rules": rules}


@router.get("/ops-command-center")
def get_ops_command_center(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    last_webhook_at = db.execute(select(func.max(WebhookEvent.received_at))).scalar_one_or_none()
    last_webhook_iso = last_webhook_at.isoformat() if last_webhook_at else None
    webhook_age_minutes = None
    if last_webhook_at:
        webhook_age_minutes = int((datetime.now(timezone.utc) - last_webhook_at).total_seconds() // 60)

    total_signals = db.execute(select(func.count(Signal.id)).where(Signal.created_at >= since)).scalar() or 0
    decision_rows = db.execute(
        select(SignalDecision.decision, func.count(SignalDecision.id).label("cnt"))
        .join(Signal, Signal.id == SignalDecision.signal_row_id)
        .where(Signal.created_at >= since)
        .group_by(SignalDecision.decision)
    ).all()
    decisions = {row.decision: int(row.cnt or 0) for row in decision_rows}

    tg_row = db.execute(
        select(
            func.sum(case((TelegramMessage.delivery_status == "SENT", 1), else_=0)).label("sent_count"),
            func.sum(case((TelegramMessage.delivery_status == "FAILED", 1), else_=0)).label("failed_count"),
        )
        .join(Signal, Signal.id == TelegramMessage.signal_row_id)
        .where(Signal.created_at >= since)
    ).one()
    sent_count = int(tg_row.sent_count or 0)
    failed_count = int(tg_row.failed_count or 0)
    tg_total = sent_count + failed_count

    outcome_row = db.execute(
        select(
            func.sum(case((SignalOutcome.outcome_status == "OPEN", 1), else_=0)).label("open_count"),
            func.sum(case((SignalOutcome.outcome_status == "CLOSED", 1), else_=0)).label("closed_count"),
            func.sum(case((SignalOutcome.outcome_status == "CLOSED", case((SignalOutcome.is_win.is_(True), 1), else_=0)), else_=0)).label("wins"),
            func.avg(case((SignalOutcome.outcome_status == "CLOSED", SignalOutcome.r_multiple), else_=None)).label("avg_r"),
            func.sum(case((SignalOutcome.outcome_status == "CLOSED", SignalOutcome.r_multiple), else_=0)).label("total_r"),
        )
        .join(Signal, Signal.id == SignalOutcome.signal_row_id)
        .where(Signal.created_at >= since)
    ).one()
    open_outcomes = int(outcome_row.open_count or 0)
    closed_outcomes = int(outcome_row.closed_count or 0)
    wins = int(outcome_row.wins or 0)

    recent_signal_rows = db.execute(
        select(
            Signal.signal_id,
            Signal.symbol,
            Signal.timeframe,
            Signal.side,
            Signal.signal_type,
            Signal.strategy,
            Signal.entry_price,
            Signal.risk_reward,
            Signal.indicator_confidence,
            Signal.created_at,
            SignalDecision.decision,
            SignalDecision.decision_reason,
            SignalDecision.telegram_route,
        )
        .outerjoin(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .where(Signal.created_at >= since)
        .order_by(Signal.created_at.desc())
        .limit(10)
    ).all()
    recent_signals = [
        {
            "signal_id": row.signal_id,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "side": row.side,
            "signal_type": row.signal_type,
            "strategy": row.strategy,
            "entry_price": float(row.entry_price) if row.entry_price is not None else None,
            "risk_reward": float(row.risk_reward) if row.risk_reward is not None else None,
            "confidence": float(row.indicator_confidence) if row.indicator_confidence is not None else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "decision": row.decision,
            "decision_reason": row.decision_reason,
            "telegram_route": row.telegram_route,
        }
        for row in recent_signal_rows
    ]

    recent_outcome_rows = db.execute(
        select(
            Signal.signal_id,
            SignalDecision.decision,
            SignalDecision.telegram_route,
            Signal.side,
            Signal.timeframe,
            Signal.signal_type,
            SignalOutcome.close_reason,
            SignalOutcome.r_multiple,
            SignalOutcome.pnl_pct,
            SignalOutcome.closed_at,
            SignalOutcome.outcome_status,
        )
        .join(Signal, Signal.id == SignalOutcome.signal_row_id)
        .outerjoin(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .where(Signal.created_at >= since)
        .order_by(SignalOutcome.created_at.desc())
        .limit(10)
    ).all()
    recent_outcomes = [
        {
            "signal_id": row.signal_id,
            "decision": row.decision,
            "route": row.telegram_route,
            "side": row.side,
            "timeframe": row.timeframe,
            "signal_type": row.signal_type,
            "close_reason": row.close_reason,
            "r_multiple": float(row.r_multiple) if row.r_multiple is not None else None,
            "pnl_pct": float(row.pnl_pct) if row.pnl_pct is not None else None,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "outcome_status": row.outcome_status,
        }
        for row in recent_outcome_rows
    ]

    alerts = []
    if webhook_age_minutes is not None and webhook_age_minutes > 30:
        alerts.append(
            {
                "code": "STALE_WEBHOOK",
                "severity": "MEDIUM",
                "value": webhook_age_minutes,
                "threshold": 30,
                "message": f"Last webhook was {webhook_age_minutes} minutes ago",
                "action": "Check TradingView alert status",
            }
        )

    config_version = 1 if ConfigRepository(db).get_signal_bot_config() else 0

    return {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "health": {
            "api": "OK",
            "database": "OK",
            "config": "OK",
            "telegram": "OK" if settings.telegram_bot_token else "FAIL",
            "webhook_freshness": "WARN" if alerts else "OK",
            "last_webhook_at": last_webhook_iso,
            "config_version": config_version,
        },
        "ops_snapshot": {
            "total_signals": int(total_signals),
            "pass_main": decisions.get("PASS_MAIN", 0),
            "pass_warning": decisions.get("PASS_WARNING", 0),
            "reject": decisions.get("REJECT", 0),
            "telegram_sent_rate": round((sent_count / tg_total), 4) if tg_total else 0.0,
            "telegram_failed": failed_count,
            "open_outcomes": open_outcomes,
            "closed_outcomes": closed_outcomes,
            "win_rate": round((wins / closed_outcomes), 4) if closed_outcomes else 0.0,
            "avg_r": round(float(outcome_row.avg_r or 0), 4),
            "total_r": round(float(outcome_row.total_r or 0), 4),
        },
        "alerts": alerts,
        "performance": {
            "main_vs_warn": [],
            "by_timeframe": [],
            "by_signal_type": [],
            "rule_performance": [],
        },
        "recent_signals": recent_signals,
        "recent_outcomes": recent_outcomes,
        "calibration_insights": [],
    }


@router.get("/export/outcomes.csv")
def export_outcomes_csv(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(
        select(
            Signal.signal_id,
            Signal.created_at,
            SignalOutcome.closed_at,
            Signal.symbol,
            Signal.timeframe,
            Signal.side,
            Signal.signal_type,
            Signal.strategy,
            SignalDecision.decision,
            SignalDecision.telegram_route,
            Signal.entry_price,
            Signal.stop_loss,
            Signal.take_profit,
            SignalOutcome.exit_price,
            SignalOutcome.close_reason,
            SignalOutcome.is_win,
            SignalOutcome.pnl_pct,
            SignalOutcome.r_multiple,
            Signal.regime,
            Signal.vol_regime,
            Signal.indicator_confidence,
            Signal.server_score,
        )
        .outerjoin(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .outerjoin(SignalOutcome, SignalOutcome.signal_row_id == Signal.id)
        .where(Signal.created_at >= since)
        .order_by(Signal.created_at.desc())
    ).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "signal_id","created_at","closed_at","symbol","timeframe","side","signal_type","strategy",
        "decision","telegram_route","entry_price","stop_loss","take_profit","exit_price","close_reason",
        "is_win","pnl_pct","r_multiple","regime","vol_regime","indicator_confidence","server_score",
        "failed_rules","warn_rules",
    ])
    for row in rows:
        writer.writerow([
            row.signal_id,
            row.created_at.isoformat() if row.created_at else "",
            row.closed_at.isoformat() if row.closed_at else "",
            row.symbol,
            row.timeframe,
            row.side,
            row.signal_type,
            row.strategy,
            row.decision,
            row.telegram_route,
            float(row.entry_price) if row.entry_price is not None else "",
            float(row.stop_loss) if row.stop_loss is not None else "",
            float(row.take_profit) if row.take_profit is not None else "",
            float(row.exit_price) if row.exit_price is not None else "",
            row.close_reason,
            row.is_win,
            float(row.pnl_pct) if row.pnl_pct is not None else "",
            float(row.r_multiple) if row.r_multiple is not None else "",
            row.regime,
            row.vol_regime,
            float(row.indicator_confidence) if row.indicator_confidence is not None else "",
            float(row.server_score) if row.server_score is not None else "",
            "",
            "",
        ])
    return Response(content=output.getvalue(), media_type="text/csv")


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


@router.get("/reject-stats")
def get_reject_stats(
    group_by: str = Query(default="", description="Comma-separated: signal_type,reject_code"),
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_dashboard_auth),
):
    """
    Reject analytics với optional group_by dimensions.
    group_by=signal_type,reject_code → group by both.
    group_by=signal_type → group by signal_type only.
    group_by=reject_code → group by reject_code only.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Parse tokens in caller order, validate against whitelist
    tokens = [t.strip() for t in group_by.split(",") if t.strip()]
    valid_tokens = [t for t in tokens if t in _ALLOWED_GROUP_BY]
    if not valid_tokens:
        # Fallback: simple total rejects
        total = db.execute(
            select(func.count(SignalDecision.id))
            .join(Signal, Signal.id == SignalDecision.signal_row_id)
            .where(
                Signal.created_at >= since,
                SignalDecision.decision == "REJECT",
            )
        ).scalar() or 0
        return {"period_days": days, "total_rejects": total, "buckets": []}

    # Deduplicate: each REJECT signal counted once, pick primary FAIL by severity.
    # Severity order: CRITICAL=0, HIGH=1, MEDIUM=2, LOW=3
    # Tie-breaker: created_at ASC, id ASC (Finding #1 fix).
    severity_order_num = case(
        (SignalFilterResult.severity == text("'CRITICAL'"), 0),
        (SignalFilterResult.severity == text("'HIGH'"), 1),
        (SignalFilterResult.severity == text("'MEDIUM'"), 2),
        (SignalFilterResult.severity == text("'LOW'"), 3),
        else_=4,
    )

    from sqlalchemy.orm import aliased

    # Window-based approach: ROW_NUMBER() per signal_row_id ordered by
    # (severity priority, created_at ASC, id ASC) ensures deterministic
    # selection even when multiple FAILs share the same severity.
    ranked = (
        select(
            SignalFilterResult.id,
            SignalFilterResult.signal_row_id,
            SignalFilterResult.rule_code,
            func.row_number()
            .over(
                partition_by=SignalFilterResult.signal_row_id,
                order_by=[severity_order_num, SignalFilterResult.created_at.asc(), SignalFilterResult.id.asc()],
            )
            .label("rn"),
        )
        .join(SignalDecision, SignalDecision.signal_row_id == SignalFilterResult.signal_row_id)
        .where(
            SignalDecision.decision == "REJECT",
            SignalFilterResult.result == "FAIL",
        )
        .subquery()
    )

    primary_fail_subq = (
        select(
            ranked.c.signal_row_id,
            ranked.c.rule_code,
        )
        .where(ranked.c.rn == 1)
        .subquery()
    )

    # Join signals with primary FAIL and aggregate
    reject_rows = (
        select(
            Signal.signal_type,
            primary_fail_subq.c.rule_code,
            func.count().label("cnt"),
        )
        .join(primary_fail_subq, primary_fail_subq.c.signal_row_id == Signal.id)
        .join(SignalDecision, SignalDecision.signal_row_id == Signal.id)
        .where(
            Signal.created_at >= since,
            SignalDecision.decision == "REJECT",
        )
        .group_by(Signal.signal_type, primary_fail_subq.c.rule_code)
    )

    rows = db.execute(reject_rows).all()

    # Build buckets using the EXACT token order from the caller
    counts: dict[tuple, int] = {}
    for signal_type, rule_code, cnt in rows:
        reject_code = rule_code_to_reject_code(rule_code)
        st = signal_type or "UNKNOWN"
        rc = reject_code or "UNKNOWN"

        # Build key in caller token order
        key = tuple(st if t == "signal_type" else rc for t in valid_tokens)
        counts[key] = counts.get(key, 0) + cnt

    return {
        "period_days": days,
        "group_by": ",".join(valid_tokens),
        "buckets": [
            {**{t: v for t, v in zip(valid_tokens, key)}, "count": c}
            for key, c in sorted(counts.items())
        ],
    }
